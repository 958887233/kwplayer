#!/bin/sh

# Step 2 of i18n - generate mo file and install it

PO_DIR='../po'

cd $PO_DIR

msgfmt --output-file=../share/locale/zh_CN/LC_MESSAGES/kuwo.mo zh_CN.po
echo 'zh_CN.mo generated and installed..'

msgfmt --output-file=../share/locale/zh_TW/LC_MESSAGES/kuwo.mo zh_TW.po
echo 'zh_TW.mo generated and installed..'

exit 0
