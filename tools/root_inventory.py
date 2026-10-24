"""Fixed read-only checks after a model-specific temporary root check."""

FRAMEWORK_FILES = {
    name: f"/usr/share/dotnet.tizen/framework/{name}"
    for name in ("Tizen.NUI.dll", "Tizen.Applications.Common.dll", "Tizen.System.dll", "Tizen.dll")
}

BACKUP_FILES = {
    "package-registry.db": ".pkgmgr_parser.db",
    "app-context.db": ".app-context.db",
    "webappservice.db": ".webappservice.db",
    "preferences-before.txt": "preferences-before.txt",
    "original-metadata.txt": "original-metadata.txt",
    "original-assembly.sha256": "original-assembly.sha256",
    "bixby-promotion-original.tar.gz": "bixby-promotion-original.tar.gz",
}

ROOT_INVENTORY_COMMANDS = (
    (
        "platform",
        "cat /etc/os-release; uname -srmo; getconf LONG_BIT; "
        "readlink -f /usr/share/dotnet.tizen/netcoreapp",
    ),
    (
        "framework_paths",
        "find /usr/share/dotnet.tizen -name Tizen.NUI.dll "
        "-o -name Tizen.Applications.Common.dll "
        "-o -name Tizen.System.dll -o -name Tizen.dll",
    ),
    (
        "framework_sizes",
        "stat -c '%n|%s' /usr/share/dotnet.tizen/framework/Tizen.NUI.dll "
        "/usr/share/dotnet.tizen/framework/Tizen.Applications.Common.dll "
        "/usr/share/dotnet.tizen/framework/Tizen.System.dll "
        "/usr/share/dotnet.tizen/framework/Tizen.dll",
    ),
    (
        "backup_candidates",
        "for p in /opt/dbspace/.pkgmgr_parser.db /opt/dbspace/.app-context.db "
        "/opt/dbspace/.webappservice.db "
        "/opt/usr/apps/com.samsung.tv.bixby-promotion/bin/BixbyPromotion.dll "
        "/opt/usr/apps/com.samsung.tv.bixby-promotion/res/quiet-home; do "
        "if [ -e \"$p\" ]; then stat -c '%n|%s|%u:%g|%a' \"$p\"; "
        "else echo missing: \"$p\"; fi; done; "
        "du -sk /opt/usr/apps/com.samsung.tv.bixby-promotion; "
        "df -k /opt/usr/share; "
        "sha256sum /opt/usr/apps/com.samsung.tv.bixby-promotion/bin/BixbyPromotion.dll",
    ),
    (
        "backup_directories",
        "if [ -d /opt/usr/share/quiet-tizen-backups ]; then "
        "find /opt/usr/share/quiet-tizen-backups -mindepth 1 -maxdepth 1 -type d; "
        "else echo none; fi",
    ),
    (
        "launcher_container_labels",
        "ls -ldZ /opt/usr/apps/com.samsung.tv.bixby-promotion "
        "/opt/usr/apps/com.samsung.tv.bixby-promotion/bin "
        "/opt/usr/apps/com.samsung.tv.bixby-promotion/bin/BixbyPromotion.dll "
        "/opt/usr/apps/com.samsung.tv.bixby-promotion/res; "
        "if [ -d /opt/usr/apps/com.samsung.tv.bixby-promotion/bin/.native_image ]; "
        "then du -sk /opt/usr/apps/com.samsung.tv.bixby-promotion/bin/.native_image; "
        "else echo native-image-absent; fi",
    ),
    (
        "preview_state",
        "if [ -f /tmp/quiet-home-state.txt ]; then cat /tmp/quiet-home-state.txt; "
        "else echo quiet-home-state-absent; fi; "
        "find /opt/usr/share/quiet-tizen-backups -maxdepth 2 -name restore-preview.sh -type f",
    ),
    (
        "installed_app_registry",
        "sqlite3 -readonly -separator '|' /opt/dbspace/.pkgmgr_parser.db "
        "'SELECT app_id,app_disable,app_onboot,app_autorestart,app_preload,app_root_path "
        "FROM package_app_info ORDER BY app_id;'",
    ),
    (
        "settings_key_routes",
        "sqlite3 -readonly -separator '|' /opt/dbspace/.app-context.db "
        "\"SELECT appid,key,target_selector,args FROM key_filter "
        "WHERE key IN ('XF86More','XF86SysMenu') ORDER BY appid,key;\"",
    ),
    ("home_preference", "vconftool get db/appfw/home_appid"),
    ("startup_preference", "vconftool get db/appfw/startup_appid"),
    (
        "service_conditions",
        "systemctl cat pisa-service.service canalysis-service.service",
    ),
)
