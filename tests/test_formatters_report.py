"""Tests for app/formatters/report.py"""

import pytest
from unittest.mock import patch, Mock
from datetime import date
from html import escape

from app.formatters.report import (
    format_idr,
    paginate_rows,
    build_header,
    build_table,
    build_summary,
    count_issues,
    build_report
)


class TestFormatIdr:
    """Test format_idr function"""
    
    @patch('app.formatters.report.format_price')
    def test_format_idr_with_number(self, mock_format_price):
        """Test formatting number with format_price"""
        mock_format_price.return_value = "1 000"
        
        result = format_idr(1000)
        
        mock_format_price.assert_called_once_with(1000, currency="", decimal_places=0)
        assert result == "1 000"
    
    @patch('app.formatters.report.format_price')
    def test_format_idr_with_exception(self, mock_format_price):
        """Test format_idr returns dash on exception"""
        mock_format_price.side_effect = Exception("Test error")
        
        result = format_idr("invalid")
        
        assert result == "—"
    
    def test_format_idr_with_none(self):
        """Test format_idr with None value"""
        result = format_idr(None)
        assert result == "—"


class TestPaginateRows:
    """Test paginate_rows function"""
    
    def test_paginate_empty_list(self):
        """Test paginating empty list"""
        result = paginate_rows([], page_size=10)
        assert result == []
    
    def test_paginate_small_list(self):
        """Test paginating list smaller than page size"""
        rows = [1, 2, 3]
        result = paginate_rows(rows, page_size=10)
        assert result == [[1, 2, 3]]
    
    def test_paginate_exact_page_size(self):
        """Test paginating list exactly matching page size"""
        rows = list(range(10))
        result = paginate_rows(rows, page_size=10)
        assert result == [list(range(10))]
    
    def test_paginate_multiple_pages(self):
        """Test paginating list into multiple pages"""
        rows = list(range(25))
        result = paginate_rows(rows, page_size=10)
        assert len(result) == 3
        assert result[0] == list(range(10))
        assert result[1] == list(range(10, 20))
        assert result[2] == list(range(20, 25))
    
    def test_paginate_default_page_size(self):
        """Test default page size of 40"""
        rows = list(range(100))
        result = paginate_rows(rows)
        assert len(result) == 3
        assert len(result[0]) == 40
        assert len(result[1]) == 40
        assert len(result[2]) == 20


class TestBuildHeader:
    """Test build_header function"""
    
    def test_build_header_normal(self):
        """Test building header with normal data"""
        result = build_header("Test Supplier", "2024-01-15")
        expected = (
            "<b>Supplier:</b> Test Supplier\n"
            "<b>Invoice date:</b> 2024-01-15\n\n"
        )
        assert result == expected
    
    def test_build_header_escapes_html(self):
        """Test header escapes HTML characters"""
        result = build_header("<script>alert('xss')</script>", "2024-01-15")
        assert "&lt;script&gt;" in result
        assert "<script>" not in result
    
    def test_build_header_with_special_chars(self):
        """Test header with special characters"""
        result = build_header("Test & Co.", "2024-01-15")
        assert "Test &amp; Co." in result
    
    def test_build_header_with_none_values(self):
        """Test header handles None values"""
        result = build_header(None, None)
        assert "<b>Supplier:</b> None" in result
        assert "<b>Invoice date:</b> None" in result


class TestBuildTable:
    """Test build_table function"""
    
    def test_build_table_empty(self):
        """Test building table with no rows"""
        result = build_table([])
        assert "# NAME" in result
        assert "QTY" in result
        assert "UNIT" in result
        assert "PRICE" in result
        assert "\n—" in result
    
    def test_build_table_single_row(self):
        """Test building table with single row"""
        rows = [{
            "name": "Test Item",
            "qty": 10,
            "unit": "kg",
            "price": 100,
            "status": "ok"
        }]
        result = build_table(rows)
        
        # Check header
        assert "# NAME" in result
        assert "QTY" in result
        
        # Check row content
        assert "1 Test Item" in result
        assert "10" in result
        assert "kg" in result
        assert "100" in result
        assert "✓" in result
    
    def test_build_table_with_errors(self):
        """Test building table with error status"""
        rows = [{
            "name": "Error Item",
            "qty": 5,
            "unit": "pcs",
            "price": 50,
            "status": "unknown"
        }]
        result = build_table(rows)
        
        # Error items should be bold
        assert "<b>Error Item</b>" in result
        assert "<b>5</b>" in result
        assert "<b>pcs</b>" in result
        assert "<b>50</b>" in result
        assert "❗" in result
    
    def test_build_table_long_name_truncation(self):
        """Test that long names are truncated"""
        rows = [{
            "name": "Very Long Product Name That Should Be Truncated",
            "qty": 1,
            "unit": "pcs",
            "price": 10,
            "status": "ok"
        }]
        result = build_table(rows)
        
        # Name should be truncated with ellipsis
        assert "…" in result
        lines = result.split('\n')
        # Get the data line (skip header)
        data_line = lines[1]
        # Extract just the name part
        name_part = data_line.split()[1]  # Skip the number
        assert len(name_part) <= 13  # name_width - 1
    
    def test_build_table_price_formatting(self):
        """Test price formatting with thousand separators"""
        rows = [{
            "name": "Item",
            "qty": 1,
            "unit": "pcs",
            "price": 240000,
            "status": "ok"
        }]
        result = build_table(rows)
        
        # Price should be formatted with spaces
        assert "240 000" in result
    
    def test_build_table_matched_name(self):
        """Test using matched_name when available"""
        rows = [{
            "name": "Original",
            "matched_name": "Matched Product",
            "qty": 1,
            "unit": "pcs",
            "price": 10,
            "status": "ok"
        }]
        result = build_table(rows)
        
        assert "Matched Product" in result
        assert "Original" not in result
    
    def test_build_table_html_escaping(self):
        """Test HTML escaping in table content"""
        rows = [{
            "name": "<script>alert('xss')</script>",
            "qty": 1,
            "unit": "<b>kg</b>",
            "price": 10,
            "status": "ok"
        }]
        result = build_table(rows)
        
        assert "&lt;script&gt;" in result
        assert "<script>" not in result
        assert "&lt;b&gt;kg&lt;/b&gt;" in result


class TestBuildSummary:
    """Test build_summary function"""
    
    @patch('app.formatters.report.t')
    def test_build_summary_no_errors(self, mock_t):
        """Test summary with no errors"""
        mock_t.return_value = "No errors. All items recognized correctly."
        
        match_results = [
            {"status": "ok", "name": "Item 1"},
            {"status": "ok", "name": "Item 2"},
            {"status": "manual", "name": "Item 3"}
        ]
        
        result = build_summary(match_results)
        
        assert "No errors" in result
        assert "Correct: 3" in result
        assert "Issues: 0" in result
    
    @patch('app.formatters.report.t')
    def test_build_summary_with_unknown_status(self, mock_t):
        """Test summary with unknown status"""
        mock_t.side_effect = lambda key, params=None: {
            "report.name_error": "item not recognized",
            "report.error_line": f"Line {params.get('line')} {params.get('name')}: {params.get('problem')}"
        }.get(key, "")
        
        match_results = [
            {"status": "unknown", "name": "Unknown Item"},
            {"status": "ok", "name": "Good Item"}
        ]
        
        result = build_summary(match_results)
        
        assert "Line 1" in result
        assert "Unknown Item" in result
        assert "check name" in result
        assert "Correct: 1" in result
        assert "Issues: 1" in result
    
    def test_build_summary_with_missing_data(self):
        """Test summary with missing quantity and price"""
        match_results = [
            {"status": "ok", "name": "Item 1", "qty": None, "price": 100},
            {"status": "ok", "name": "Item 2", "qty": 10, "price": None}
        ]
        
        result = build_summary(match_results)
        
        assert "Line 1" in result
        assert "missing quantity" in result
        assert "Line 2" in result
        assert "missing price" in result
        assert "Issues: 2" in result
    
    def test_build_summary_with_validation_issues(self):
        """Test summary with validation issues"""
        match_results = [{
            "status": "ok",
            "name": "Item",
            "qty": 10,
            "price": 100,
            "issues": [
                {"type": "ARITHMETIC_ERROR"},
                {"type": "PRICE_ZERO_LOST", "fix": "1000"},
                {"type": "UNIT_MISMATCH", "suggestion": "kg"}
            ]
        }]
        
        result = build_summary(match_results)
        
        assert "check math" in result
        assert "price missing 0: 1000" in result
        assert "should be kg" in result
    
    @patch('app.formatters.report.t')
    def test_build_summary_status_priorities(self, mock_t):
        """Test different status types"""
        # Setup translations
        mock_t.side_effect = lambda key, params=None: {
            "report.unit_mismatch": "unit mismatch error",
            "report.processing_error": "processing error"
        }.get(key, "")
        
        match_results = [
            {"status": "unit_mismatch", "name": "Item 1"},
            {"status": "error", "name": "Item 2"},
            {"status": "manual", "name": "Item 3"},
            {"status": "ok", "name": "Item 4"}
        ]
        
        result = build_summary(match_results)
        
        assert "check unit" in result
        assert "processing error" in result
        assert "Correct: 2" in result  # manual + ok
        assert "Issues: 2" in result  # unit_mismatch + error


class TestCountIssues:
    """Test count_issues function"""
    
    def test_count_issues_empty(self):
        """Test counting issues in empty list"""
        assert count_issues([]) == 0
    
    def test_count_issues_all_ok(self):
        """Test counting when all items are ok"""
        match_results = [
            {"status": "ok"},
            {"status": "ok"},
            {"status": "ok"}
        ]
        assert count_issues(match_results) == 0
    
    def test_count_issues_mixed(self):
        """Test counting mixed statuses"""
        match_results = [
            {"status": "ok"},
            {"status": "unknown"},
            {"status": "error"},
            {"status": "unit_mismatch"},
            {"status": "manual"}  # Should count as issue
        ]
        assert count_issues(match_results) == 4
    
    def test_count_issues_no_status(self):
        """Test items without status field"""
        match_results = [
            {},
            {"status": "ok"},
            {"other": "field"}
        ]
        assert count_issues(match_results) == 2


class TestBuildReport:
    """Test build_report function"""
    
    def test_build_report_with_dict_input(self):
        """Test report with dictionary input"""
        parsed_data = {
            "supplier": "Test Supplier",
            "date": "2024-01-15"
        }
        match_results = [
            {"name": "Item 1", "qty": 10, "unit": "kg", "price": 100, "status": "ok"}
        ]
        
        report, has_errors = build_report(parsed_data, match_results)
        
        assert "<b>Supplier:</b> Test Supplier" in report
        assert "<b>Invoice date:</b> 2024-01-15" in report
        assert "<pre>" in report
        assert "</pre>" in report
        assert not has_errors
    
    def test_build_report_with_object_input(self):
        """Test report with object input"""
        parsed_data = Mock()
        parsed_data.supplier = "Object Supplier"
        parsed_data.date = date(2024, 1, 15)
        
        match_results = [
            {"name": "Item 1", "qty": 10, "unit": "kg", "price": 100, "status": "ok"}
        ]
        
        report, has_errors = build_report(parsed_data, match_results)
        
        assert "Object Supplier" in report
        assert "2024-01-15" in report
        assert not has_errors
    
    def test_build_report_with_errors(self):
        """Test report identifies errors correctly"""
        parsed_data = {"supplier": "Test", "date": "2024-01-15"}
        match_results = [
            {"name": "Item 1", "qty": 10, "unit": "kg", "price": 100, "status": "unknown"},
            {"name": "Item 2", "qty": None, "unit": "pcs", "price": 50, "status": "ok"}
        ]
        
        report, has_errors = build_report(parsed_data, match_results)
        
        assert has_errors
        assert "Issues: 2" in report
    
    def test_build_report_pagination(self):
        """Test report pagination"""
        parsed_data = {"supplier": "Test", "date": "2024-01-15"}
        
        # Create 100 items
        match_results = []
        for i in range(100):
            match_results.append({
                "name": f"Item {i+1}",
                "qty": 10,
                "unit": "kg",
                "price": 100,
                "status": "ok"
            })
        
        # First page
        report1, _ = build_report(parsed_data, match_results, page=1, page_size=40)
        assert "Item 1" in report1
        assert "Item 40" in report1
        assert "Item 41" not in report1
        
        # Second page
        report2, _ = build_report(parsed_data, match_results, page=2, page_size=40)
        assert "Item 1" not in report2
        assert "Item 41" in report2
        assert "Item 80" in report2
    
    def test_build_report_html_escaping(self):
        """Test HTML escaping in report"""
        parsed_data = {
            "supplier": "<script>alert('xss')</script>",
            "date": "2024-01-15"
        }
        match_results = []
        
        report, _ = build_report(parsed_data, match_results)
        
        assert "&lt;script&gt;" in report
        assert "<script>" not in report
    
    def test_build_report_missing_data(self):
        """Test report with missing supplier/date"""
        parsed_data = {}
        match_results = []
        
        report, _ = build_report(parsed_data, match_results)
        
        assert "Unknown supplier" in report
        assert "—" in report  # Missing date