#!/bin/bash
# usage: shots.sh <port> <prefix>  -> PNGs next to this script (Windows Edge, headless)
E="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
WIN='C:\Users\Admin\AppData\Local\Temp'
here=$(cd "$(dirname "$0")" && pwd)
for theme in light dark; do
  for spec in "home:1440:1000:2000:shot=home&" "chat-empty:1440:900:2000:shot=chat-empty&" "chat:1440:1400:14000:shot=chat&" "answer:1440:2200:14000:shot=answer&" "monitor:1440:1500:3000:shot=monitor&" "access:1440:900:3000:shot=access&" "ratings:1440:900:3000:shot=ratings&" "report:1440:1500:3000:shot=report&" "collapsed:1440:900:3000:shot=collapsed&" "feedback:1440:1500:14000:shot=feedback&" "phone:520:1500:3000:PHONE"; do
    IFS=: read name w h budget extra <<<"$spec"
    out="$2-$theme-$name"
    timeout 90 "$E" --headless=new --disable-gpu --hide-scrollbars --window-size=$w,$h --virtual-time-budget=$budget \
      $( [ "$name" = answer ] || [ "$name" = chat ] || [ "$name" = feedback ] && echo --force-prefers-reduced-motion ) \
      --user-data-dir="$WIN\\edge-shot" --screenshot="$WIN\\$out.png" "$( [ "$extra" = PHONE ] && echo "http://localhost:$1/phone.html?theme=$theme" || echo "http://localhost:$1/?${extra}theme=$theme" )" >/dev/null 2>&1
    mv "/mnt/c/Users/Admin/AppData/Local/Temp/$out.png" "$here/"
  done
done
