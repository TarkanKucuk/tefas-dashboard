import borsapy as bp

TEST_FUNDS = ["PBR", "PHE", "TLY"]

for kod in TEST_FUNDS:
    print(f"\n=== {kod} ===")
    try:
        fund = bp.Fund(kod)
        df = fund.allocation
        print(df)
    except Exception as e:
        print(f"HATA: {type(e).__name__}: {e}")
