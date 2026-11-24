#!/bin/bash
# uso: _loop.sh <prefixo> <alvos...>  (corre 10 vezes)
cd /d/DEKSTOP/puzzle_piece_finder
d=docs/diagnostico/gui/intermitente
pre=$1; shift
for i in 01 02 03 04 05 06 07 08 09 10; do
 s=$(date +%s)
 .venv/Scripts/python.exe -m pytest "$@" -x --tb=short -p no:cacheprovider -rf > $d/${pre}_$i.txt 2>&1
 echo "$i rc=$? $(( $(date +%s)-s ))s" >> $d/${pre}_rcs.txt
done
echo done >> $d/${pre}_rcs.txt
