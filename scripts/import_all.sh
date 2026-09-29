#!/bin/sh
# Import CSVs dropped in data/. Missing files are skipped.
# Optional downloads, not run here (each needs a Kaggle login and is large):
#   kagglehub.dataset_download("mlg-ulb/creditcardfraud")
#   kagglehub.dataset_download("kartik2112/fraud-detection")
#   kagglehub.dataset_download("sgpjesus/bank-account-fraud-dataset-neurips-2022")
set -e
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=".venv/bin/python"

import_detected() {
  file="$1"
  name="$2"
  if [ ! -f "data/$file" ]; then
    echo "Skipping $name (data/$file not found)"
    return 0
  fi
  echo "Importing $name from $file"
  PYTHONPATH=. "$PY" -m ml.import_dataset --path "data/$file" --name "$name"
}

import_mapped() {
  file="$1"
  name="$2"
  mapping="$3"
  if [ ! -f "data/$file" ]; then
    echo "Skipping $name (data/$file not found)"
    return 0
  fi
  echo "Importing $name from $file"
  PYTHONPATH=. "$PY" -m ml.import_dataset --path "data/$file" --name "$name" --map "$mapping"
}

if [ -f data/creditcard.csv ]; then
  echo "Skipping creditcard (data/creditcard.csv). The live champion is already installed under train/."
fi

import_detected "PS_20174392719_1491204439457_log.csv" paysim
import_detected "train_transaction.csv" ieee_cis
import_detected "fraudTrain.csv" sparkov

import_mapped "Base.csv" nubank_baf \
  "time=days_since_request,amount=intended_amount,label=fraud_bool,user=customer_id,city=city,device=device_os"
import_mapped "Fraud_Data.csv" ecommerce_fraud \
  "time=purchase_time,amount=amount,label=class,user=user_id,device=device_id"
import_mapped "upi_fraud.csv" upi_india \
  "time=timestamp,amount=amount,label=is_fraud,user=sender_vpa,merchant=receiver_vpa,device=device,city=location"

echo "Import pass finished. Train with: scripts/train_all.sh"
