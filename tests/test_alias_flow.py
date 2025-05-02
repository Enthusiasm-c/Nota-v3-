import os
import tempfile
import shutil
from app import matcher, data_loader, alias

def test_alias_flow():
    # Prepare temp dirs/files
    tmpdir = tempfile.mkdtemp()
    base_products = os.path.join(tmpdir, "base_products.csv")
    aliases_csv = os.path.join(tmpdir, "aliases.csv")
    # Write base products
    with open(base_products, "w", encoding="utf-8") as f:
        f.write("id,alias,unit\n")
        f.write("tun001,Tuna loin,kg\n")
    # Step 1: unknown position
    positions = [{"name": "TunaX", "qty": 1, "unit": "kg"}]
    products = data_loader.load_products(base_products, aliases_csv)
    result1 = matcher.match_positions(positions, products)
    assert result1[0]["status"] == "unknown"
    # Step 2: add alias
    alias.add_alias("TunaX", "tun001", aliases_csv)
    products2 = data_loader.load_products(base_products, aliases_csv)
    result2 = matcher.match_positions(positions, products2)
    assert result2[0]["status"] == "ok"
    assert result2[0]["product_id"] == "tun001"
    # Clean up
    shutil.rmtree(tmpdir)
