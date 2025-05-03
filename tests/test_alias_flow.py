import os
import tempfile
import shutil
from app import matcher, data_loader, alias

def test_alias_flow():
    # Prepare temp dirs/files
    tmpdir = tempfile.mkdtemp()
    base_products = os.path.join(tmpdir, "base_products.csv")
    aliases_csv = os.path.join(tmpdir, "aliases.csv")
    print(f"DEBUG: aliases_csv path before any ops: {aliases_csv}")
    # Write base products
    with open(base_products, "w", encoding="utf-8") as f:
        f.write("id,alias,unit\n")
        f.write("tun001,Tuna loin,kg\n")
    # Step 1: unknown position
    positions = [{"name": "TunaX", "qty": 1, "unit": "kg"}]
    products = data_loader.load_products(base_products, aliases_csv)
    print(f"DEBUG: aliases_csv path before add_alias: {aliases_csv}")
    print('DEBUG products:', [dict(p) if hasattr(p, 'dict') else p for p in products])
    print('DEBUG positions:', positions)
    result1 = matcher.match_positions(positions, products)
    print('DEBUG result1:', result1)
    assert result1[0]["status"] == "unknown"
    # Step 2: add alias
    alias.add_alias("TunaX", "tun001", aliases_csv)
    print(f"DEBUG: aliases_csv path after add_alias: {aliases_csv}")
    products2 = data_loader.load_products(base_products, aliases_csv)
    print(f"DEBUG: aliases_csv path after load_products: {aliases_csv}")
    print('DEBUG products2:', [dict(p) if hasattr(p, 'dict') else p for p in products2])
    print('DEBUG aliases in products2:', [p.alias for p in products2 if hasattr(p, 'alias')])
    result2 = matcher.match_positions(positions, products2)
    assert result2[0]["status"] == "ok"
    assert result2[0]["product_id"] == "tun001"
    # Clean up
    shutil.rmtree(tmpdir)
