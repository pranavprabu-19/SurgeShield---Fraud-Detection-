#!/bin/sh
# Train a champion for each imported dataset that does not have one yet.
# The credit-card champion is already in the repo and is not retrained.
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

found=0
for dir in data/*/; do
  [ -d "$dir" ] || continue
  name="$(basename "$dir")"
  [ "$name" = "creditcard" ] && continue
  [ -f "data/$name/train.csv" ] || continue
  found=1
  if [ -f "ml/artifacts/$name/model.joblib" ]; then
    echo "Already trained: $name"
    continue
  fi
  echo "Training champion: $name"
  if SURGESHIELD_DATASET="$name" PYTHONPATH=. .venv/bin/python -m ml.train; then
    echo "Ready: $name"
  else
    echo "Skipping $name (training failed)"
  fi
done

if [ "$found" -eq 0 ]; then
  echo "No imported datasets under data/. Run scripts/import_all.sh first."
fi
echo "Champions on disk are listed at GET /models"
