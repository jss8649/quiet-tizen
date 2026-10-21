#!/usr/bin/env python3
"""Build locally; never redistribute Samsung reference assemblies."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["payloads", "launcher", "all"])
    parser.add_argument("--dotnet", default=os.environ.get("DOTNET", "dotnet"))
    parser.add_argument("--framework", type=Path, default=ROOT / ".local/tv-framework")
    parser.add_argument("--profile", type=Path, default=ROOT / "profiles/un75u8000ffxza-1300.9.json",
                        help="TV profile whose launcher container Quiet Home replaces")
    args = parser.parse_args()
    jobs = []
    if args.target in ("payloads", "all"):
        for name in ("SamsungTvArchiveRoot", "SamsungTvRootAgent"):
            jobs.append((ROOT / f"vendor/payload-source/{name}.csproj", "payloads", name, []))
    if args.target in ("launcher", "all"):
        for name in ("Tizen.NUI", "Tizen.Applications.Common", "Tizen.System", "Tizen"):
            if not (args.framework / f"{name}.dll").is_file():
                parser.error(f"Missing {name}.dll. Read docs/04-launcher.md; these are not bundled.")
        launcher = json.loads(args.profile.read_text())["launcher"]
        home_dll = launcher["dll"]
        common = [f"-p:TV_FRAMEWORK_DIR={args.framework.resolve()}", f"-p:QuietHomeAppId={launcher['app_id']}"]
        jobs.append((ROOT / "launcher/src/Home.csproj", "Home", "Home",
                     [*common, f"-p:AssemblyName={Path(home_dll).stem}"]))
        jobs.append((ROOT / "launcher/src/QuickLaunch.csproj", "QuickLaunch", "QuickLaunch", common))
        jobs.append((ROOT / "launcher/probe/Probe.csproj", "Probe", "Probe", []))
    for project, output, intermediate, extra in jobs:
        subprocess.run([
            args.dotnet, "build", str(project), "-c", "Release", "--nologo",
            "-o", str(ROOT / ".local/build" / output),
            f"-p:BaseIntermediateOutputPath={ROOT / '.local/obj' / intermediate}/",
            "-p:Deterministic=true",
            f"-p:PathMap={ROOT}=/_/quiet-tizen", *extra,
        ], check=True, env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})
    if args.target in ("launcher", "all"):
        destination = ROOT / ".local/package"
        # Start clean so a previous profile's entry assembly is never packaged.
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        shutil.copyfile(ROOT / ".local/build/Home" / home_dll, destination / home_dll)
        shutil.copyfile(ROOT / ".local/build/QuickLaunch/QuickLaunch.dll", destination / "QuickLaunch.dll")
        shutil.copyfile(ROOT / ".local/build/Probe/Probe.dll", destination / "Probe.dll")
        assets = destination / "quiet-home"
        shutil.copytree(ROOT / "launcher/assets", assets)
        local_catalog = ROOT / "launcher/assets/apps.local.json"
        if local_catalog.exists():
            shutil.copyfile(local_catalog, assets / "apps.json")
        (assets / "apps.local.json").unlink(missing_ok=True)
        print("Deployable files: .local/package/. Review the catalog and input mapping before use.")


if __name__ == "__main__":
    main()
