#!/bin/bash
# となり.app を組み立てる（swiftc 単体・Xcode プロジェクトなし・ad-hoc 署名。作りはアーティファクト棚と同じ）。
#   bash tonari/app/build_app.sh            # → ~/Applications/となり.app
#   bash tonari/app/build_app.sh <出力.app>
# アプリのフォルダ（tonari/）と、uv・claude・ffmpeg の場所をビルドの時点で Info.plist に焼く
# （Dock から開いたアプリはターミナルの PATH を持たないため）。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"
OUT="${1:-$HOME/Applications/となり.app}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

UV="$(command -v uv || true)"
CLAUDE="$(command -v claude || true)"
FFMPEG="$(command -v ffmpeg || true)"
for t in UV CLAUDE FFMPEG; do
  if [ -z "${!t}" ]; then echo "✗ $(echo $t | tr 'A-Z' 'a-z') が見つからない（PATH を確かめる）" >&2; exit 2; fi
done
TOOL_PATH="$(dirname "$CLAUDE"):$(dirname "$UV"):$(dirname "$FFMPEG"):/usr/bin:/bin:/usr/sbin:/sbin"

echo "▶ 文字起こしの道具"
[ -x "$APP_DIR/stt/bin/stt-helper" ] || "$APP_DIR/stt/build.sh"

echo "▶ compile"
swiftc -O -o "$WORK/Tonari" "$HERE/main.swift" -framework AppKit -framework WebKit

echo "▶ icon"
swiftc -O -o "$WORK/make_icon" "$HERE/make_icon.swift" -framework AppKit
"$WORK/make_icon" "$WORK/icon_1024.png"
mkdir -p "$WORK/AppIcon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$WORK/icon_1024.png" --out "$WORK/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d "$WORK/icon_1024.png" --out "$WORK/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$WORK/AppIcon.iconset" -o "$WORK/AppIcon.icns"

echo "▶ bundle → $OUT"
rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"
cp "$WORK/Tonari" "$OUT/Contents/MacOS/Tonari"
cp "$WORK/AppIcon.icns" "$OUT/Contents/Resources/AppIcon.icns"
cat > "$OUT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Tonari</string>
  <key>CFBundleDisplayName</key><string>となり</string>
  <key>CFBundleIdentifier</key><string>local.tonari</string>
  <key>CFBundleExecutable</key><string>Tonari</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSHasLocalizedDisplayName</key><true/>
  <key>CFBundleDevelopmentRegion</key><string>ja</string>
  <key>CFBundleLocalizations</key><array><string>ja</string><string>en</string></array>
  <key>NSMicrophoneUsageDescription</key><string>声で質問するとき、録音して文字にするために使います。録音はこの Mac の中に保存され、文字起こしのために ElevenLabs に送ることがあります。</string>
  <key>NSHumanReadableCopyright</key><string>自分専用の学びのアプリ（手元で動く）</string>
  <key>TonariAppDir</key><string>$APP_DIR</string>
  <key>TonariUV</key><string>$UV</string>
  <key>TonariPath</key><string>$TOOL_PATH</string>
  <key>TonariPort</key><string>4880</string>
</dict>
</plist>
PLIST
# 表示名も「となり」にそろえる。ファイル名を Tonari.app にしていたときは、表示名を地域化しても Spotlight が「Tonari」のまま
# 引き続けて「となり」で見つからなかった（2026-10-29）ので、ファイル名そのものを となり.app にした
mkdir -p "$OUT/Contents/Resources/ja.lproj" "$OUT/Contents/Resources/en.lproj"
printf 'CFBundleDisplayName = "となり";\nCFBundleName = "となり";\n' > "$OUT/Contents/Resources/ja.lproj/InfoPlist.strings"
printf 'CFBundleDisplayName = "Tonari";\nCFBundleName = "Tonari";\n' > "$OUT/Contents/Resources/en.lproj/InfoPlist.strings"
codesign --force --sign - "$OUT" >/dev/null 2>&1 || echo "  (codesign をスキップ)"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$OUT" 2>/dev/null || true
mdimport "$OUT" 2>/dev/null || true
echo "✓ $OUT"
