import re

params = ['name Cream Cheese', 'price 250', 'qty 15', 'unit krat']
results = []

for param in params:
    field_match = re.match(r'(название|имя|name|цена|price|количество|кол-во|qty|единица|ед\.|unit)\s+(.*)', param, re.IGNORECASE)
    if field_match:
        field_type = field_match.group(1).lower()
        field_value = field_match.group(2).strip()
        print(f'{field_type}: {field_value}')
        
        # Создаем соответствующую команду
        line_num = 3 # пример, в реальном коде это будет из внешнего match
        if field_type in ('название', 'имя', 'name'):
            results.append({"action": "set_name", "line": line_num - 1, "name": field_value})
        elif field_type in ('цена', 'price'):
            try:
                price = float(field_value.replace(',', '.'))
                results.append({"action": "set_price", "line": line_num - 1, "price": price})
            except ValueError:
                results.append({"action": "unknown", "error": "invalid_price_value"})
        elif field_type in ('количество', 'кол-во', 'qty'):
            try:
                qty = float(field_value.replace(',', '.'))
                results.append({"action": "set_qty", "line": line_num - 1, "qty": qty})
            except ValueError:
                results.append({"action": "unknown", "error": "invalid_qty_value"})
        elif field_type in ('единица', 'ед.', 'unit'):
            results.append({"action": "set_unit", "line": line_num - 1, "unit": field_value})

print(f"\nResults: {results}") 