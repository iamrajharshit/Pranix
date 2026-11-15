#!/usr/bin/env sh
# SPDX-License-Identifier: AGPL-3.0-only
# Fonts for server-rendered card images (D64). Both are SIL Open Font License 1.1.
# Cormorant Garamond (Christian Thalmann, Catharsis Fonts) pinned to a commit; Inter v4.1 (Rasmus Andersson).
set -eu
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
DEST="${1:-$SCRIPT_DIR/../data/fonts}"
CORMORANT="https://raw.githubusercontent.com/CatharsisFonts/Cormorant/016784836d2ad47bc4c62b7f504a0a5875d85aeb"
INTER_ZIP="https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
mkdir -p "$DEST"
cd "$DEST"
[ -f CormorantGaramond-SemiBold.ttf ] || curl -fsSL -o CormorantGaramond-SemiBold.ttf "$CORMORANT/fonts/ttf/CormorantGaramond-SemiBold.ttf"
[ -f Cormorant-OFL.txt ] || curl -fsSL -o Cormorant-OFL.txt "$CORMORANT/OFL.txt"
if [ ! -f Inter-Regular.ttf ] || [ ! -f Inter-SemiBold.ttf ]; then
  curl -fsSL -o inter.zip "$INTER_ZIP"
  python -c "import zipfile; z=zipfile.ZipFile('inter.zip'); [open(o,'wb').write(z.read(i)) for i,o in [('extras/ttf/Inter-Regular.ttf','Inter-Regular.ttf'),('extras/ttf/Inter-SemiBold.ttf','Inter-SemiBold.ttf'),('LICENSE.txt','Inter-OFL.txt')]]"
  rm -f inter.zip
fi
cat > SHA256SUMS <<'SUMS'
de1b7923fbc20ce742f6498d085ad0b64dc3625efbd8bdb2f01dc70e1e7a6edd  CormorantGaramond-SemiBold.ttf
60700d351cac4650c51f3f9db318d2a420f8b45052dba2715eb5fec41f0f6956  Cormorant-OFL.txt
40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82  Inter-Regular.ttf
78a843fade9d4612a5567302fb595b56976eb5fcebf4fea5a5912d638bafcde3  Inter-SemiBold.ttf
262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a  Inter-OFL.txt
SUMS
sha256sum -c SHA256SUMS
