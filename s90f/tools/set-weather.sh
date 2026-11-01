#!/bin/sh
set -eu
lat=${1:?latitude}; lon=${2:?longitude}; place=${3:?place}; units=${4:-fahrenheit}
case "$lat" in -[0-9]*|[0-9]*) ;; *) exit 2;; esac
case "$lon" in -[0-9]*|[0-9]*) ;; *) exit 2;; esac
case "$units" in fahrenheit|celsius) ;; *) exit 2;; esac
case "$place" in *[!A-Za-z0-9\ ,.-]*) exit 2;; esac
R=/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home
printf '{"Latitude": %s, "Longitude": %s, "Place": "%s", "Units": "%s"}\n' "$lat" "$lon" "$place" "$units" > "$R/weather.json"
chown 201:0 "$R/weather.json"; chmod 644 "$R/weather.json"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$R/weather.json"
rm -f /tmp/quiet-home-weather.txt
echo "weather.json written for $place"
