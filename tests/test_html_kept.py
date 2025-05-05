from app.formatters import report

def test_report_html_keeps_tags():
    parsed_data = {
        'supplier': 'Guna',
        'date': '2024-05-01',
    }
    match_results = [
        {'name': 'Milk', 'qty': 2, 'unit': 'pcs', 'line_total': 10000, 'status': 'ok'},
    ]
    html, _ = report.build_report(parsed_data, match_results)
    assert '<b>Supplier:</b>' in html
    # build_report теперь не вставляет <br>, только <pre> и \n
    assert '&lt;b&gt;' not in html
    assert '&lt;br&gt;' not in html
