name: Kontrol

on:
  workflow_dispatch:

jobs:
  kontrol:
    runs-on: ubuntu-latest
    steps:
      - name: Repoyu indir
        uses: actions/checkout@v4

      - name: Python kur
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Gerekli kütüphaneleri kur
        run: pip install pandas pyarrow tefasfon

      - name: tefasfon ham yanıtını incele
        run: python diagnose_tefasfon_raw.py
