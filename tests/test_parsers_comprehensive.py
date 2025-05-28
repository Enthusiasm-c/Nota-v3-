"""
Comprehensive tests for all parser modules.
Tests command parsing, date parsing, general parsing, line parsing, and text processing.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date, datetime
from app.parsers.command_parser import (
    parse_command,
    extract_command_type,
    parse_edit_command,
    parse_date_command,
    CommandParser
)
from app.parsers.date_parser import (
    DateParser,
    parse_date_from_text,
    extract_date_patterns,
    normalize_date_format
)
from app.parsers.general_parser import (
    GeneralParser,
    parse_invoice_structure,
    extract_invoice_metadata,
    parse_table_data
)
from app.parsers.line_parser import (
    LineParser,
    parse_invoice_line,
    extract_line_components,
    normalize_line_data
)
from app.parsers.text_processor import (
    TextProcessor,
    clean_text,
    tokenize_text,
    extract_entities,
    normalize_whitespace
)


class TestCommandParser:
    """Test suite for CommandParser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = CommandParser()
    
    def test_command_parser_init(self):
        """Test CommandParser initialization."""
        parser = CommandParser()
        
        assert parser.supported_commands is not None
        assert isinstance(parser.supported_commands, (list, dict))
    
    def test_parse_command_edit_supplier(self):
        """Test parsing edit supplier command."""
        command = "edit supplier New Supplier Name"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["command_type"] == "edit"
        assert result["field"] == "supplier"
        assert result["value"] == "New Supplier Name"
    
    def test_parse_command_edit_line_quantity(self):
        """Test parsing edit line quantity command."""
        command = "edit line 1 qty 3.5"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["command_type"] == "edit"
        assert result["target"] == "line"
        assert result["line_number"] == 1
        assert result["field"] == "qty"
        assert result["value"] == "3.5"
    
    def test_parse_command_edit_line_price(self):
        """Test parsing edit line price command."""
        command = "edit line 2 price 25000"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["line_number"] == 2
        assert result["field"] == "price"
        assert result["value"] == "25000"
    
    def test_parse_command_date(self):
        """Test parsing date command."""
        command = "date 2025-05-28"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["command_type"] == "date"
        assert result["date_value"] == "2025-05-28"
    
    def test_parse_command_send(self):
        """Test parsing send command."""
        command = "send"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["command_type"] == "send"
    
    def test_parse_command_cancel(self):
        """Test parsing cancel command."""
        command = "cancel"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["command_type"] == "cancel"
    
    def test_parse_command_help(self):
        """Test parsing help command."""
        command = "help"
        
        result = self.parser.parse_command(command)
        
        assert result["success"] is True
        assert result["command_type"] == "help"
    
    def test_parse_command_invalid(self):
        """Test parsing invalid commands."""
        invalid_commands = [
            "",
            "invalid_command",
            "edit",  # Missing parameters
            "edit line",  # Incomplete
            "edit line abc qty 1",  # Invalid line number
            "edit unknown_field value",  # Unknown field
        ]
        
        for invalid_command in invalid_commands:
            result = self.parser.parse_command(invalid_command)
            assert result["success"] is False
            assert "error" in result
    
    def test_extract_command_type(self):
        """Test command type extraction."""
        test_cases = [
            ("edit supplier Test", "edit"),
            ("send invoice", "send"),
            ("date 2025-05-28", "date"),
            ("help me", "help"),
            ("unknown command", None),
        ]
        
        for command, expected in test_cases:
            result = extract_command_type(command)
            assert result == expected
    
    def test_parse_edit_command_variations(self):
        """Test parsing various edit command formats."""
        test_cases = [
            ("edit supplier New Name", {"field": "supplier", "value": "New Name"}),
            ("edit invoice_number INV-001", {"field": "invoice_number", "value": "INV-001"}),
            ("edit line 1 name Product A", {"line_number": 1, "field": "name", "value": "Product A"}),
            ("edit line 2 unit kg", {"line_number": 2, "field": "unit", "value": "kg"}),
        ]
        
        for command, expected in test_cases:
            result = parse_edit_command(command)
            assert result["success"] is True
            for key, value in expected.items():
                assert result[key] == value
    
    def test_parse_date_command_formats(self):
        """Test parsing date commands with different formats."""
        test_cases = [
            ("date 2025-05-28", "2025-05-28"),
            ("date 28/05/2025", "28/05/2025"),
            ("date 28.05.2025", "28.05.2025"),
            ("date today", "today"),
            ("date yesterday", "yesterday"),
        ]
        
        for command, expected_date in test_cases:
            result = parse_date_command(command)
            assert result["success"] is True
            assert result["date_value"] == expected_date


class TestDateParser:
    """Test suite for DateParser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DateParser()
    
    def test_date_parser_init(self):
        """Test DateParser initialization."""
        parser = DateParser()
        
        assert parser.date_patterns is not None
        assert parser.supported_formats is not None
    
    def test_parse_date_from_text_iso_format(self):
        """Test parsing ISO format dates from text."""
        text_samples = [
            "Invoice date: 2025-05-28",
            "Date 2025-05-28 invoice",
            "2025-05-28",
        ]
        
        for text in text_samples:
            result = parse_date_from_text(text)
            assert result["success"] is True
            assert result["date"] == date(2025, 5, 28)
    
    def test_parse_date_from_text_european_format(self):
        """Test parsing European format dates."""
        text_samples = [
            "Invoice: 28.05.2025",
            "Date: 28/05/2025",
            "28-05-2025",
        ]
        
        for text in text_samples:
            result = parse_date_from_text(text)
            assert result["success"] is True
            assert result["date"] == date(2025, 5, 28)
    
    def test_parse_date_from_text_multiple_dates(self):
        """Test parsing text with multiple dates."""
        text = "Created: 2025-05-27, Invoice: 2025-05-28, Due: 2025-06-28"
        
        result = self.parser.parse_date_from_text(text)
        
        assert result["success"] is True
        assert len(result["dates"]) == 3
        assert result["primary_date"] == date(2025, 5, 28)  # Invoice date preferred
    
    def test_parse_date_from_text_no_date(self):
        """Test parsing text with no dates."""
        text = "This text has no dates"
        
        result = parse_date_from_text(text)
        
        assert result["success"] is False
        assert result["date"] is None
    
    def test_extract_date_patterns(self):
        """Test date pattern extraction."""
        text = "Invoice 28.05.2025 total 100000"
        
        patterns = extract_date_patterns(text)
        
        assert len(patterns) >= 1
        assert any("28.05.2025" in pattern for pattern in patterns)
    
    def test_normalize_date_format(self):
        """Test date format normalization."""
        test_cases = [
            ("28.05.2025", "2025-05-28"),
            ("28/05/2025", "2025-05-28"),
            ("28-05-2025", "2025-05-28"),
            ("2025-05-28", "2025-05-28"),
        ]
        
        for input_date, expected in test_cases:
            result = normalize_date_format(input_date)
            assert result == expected
    
    def test_parse_relative_dates(self):
        """Test parsing relative date expressions."""
        relative_expressions = [
            "today",
            "yesterday", 
            "tomorrow",
            "last week",
            "next month",
        ]
        
        for expression in relative_expressions:
            result = self.parser.parse_relative_date(expression)
            assert result["success"] is True
            assert isinstance(result["date"], date)
    
    def test_parse_month_names(self):
        """Test parsing dates with month names."""
        text_samples = [
            "28 May 2025",
            "May 28, 2025",
            "28 мая 2025",  # Russian
            "28 Mei 2025",  # Indonesian
        ]
        
        for text in text_samples:
            result = self.parser.parse_date_from_text(text)
            if result["success"]:  # Not all month names may be supported
                assert result["date"].month == 5
                assert result["date"].year == 2025


class TestGeneralParser:
    """Test suite for GeneralParser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = GeneralParser()
        
        self.sample_invoice_text = """
        INVOICE
        Supplier: Test Supplier Ltd
        Invoice Number: INV-2025-001
        Date: 28.05.2025
        
        Product A    2 kg    15000    30000
        Product B    1 pcs   25000    25000
        
        Total: 55000
        """
    
    def test_general_parser_init(self):
        """Test GeneralParser initialization."""
        parser = GeneralParser()
        
        assert parser.patterns is not None
        assert parser.extractors is not None
    
    def test_parse_invoice_structure(self):
        """Test parsing complete invoice structure."""
        result = parse_invoice_structure(self.sample_invoice_text)
        
        assert result["success"] is True
        assert "metadata" in result
        assert "lines" in result
        assert "totals" in result
    
    def test_extract_invoice_metadata(self):
        """Test extracting invoice metadata."""
        result = extract_invoice_metadata(self.sample_invoice_text)
        
        assert result["success"] is True
        assert result["supplier"] == "Test Supplier Ltd"
        assert result["invoice_number"] == "INV-2025-001"
        assert result["date"] == date(2025, 5, 28)
    
    def test_parse_table_data(self):
        """Test parsing table data from invoice."""
        table_text = """
        Product A    2 kg    15000    30000
        Product B    1 pcs   25000    25000
        """
        
        result = parse_table_data(table_text)
        
        assert result["success"] is True
        assert len(result["lines"]) == 2
        
        line1 = result["lines"][0]
        assert line1["name"] == "Product A"
        assert line1["qty"] == 2.0
        assert line1["unit"] == "kg"
        assert line1["price"] == 15000.0
        assert line1["amount"] == 30000.0
    
    def test_parse_multiformat_invoice(self):
        """Test parsing invoices in different formats."""
        formats = [
            # Tab-separated
            "Product A\t2\tkg\t15000\t30000",
            # Comma-separated
            "Product A, 2, kg, 15000, 30000",
            # Space-separated with alignment
            "Product A     2 kg   15000   30000",
        ]
        
        for format_text in formats:
            result = self.parser.parse_table_data(format_text)
            if result["success"]:  # Some formats may not be fully supported
                assert len(result["lines"]) >= 1
                assert result["lines"][0]["name"] == "Product A"
    
    def test_extract_totals(self):
        """Test extracting total amounts."""
        total_text = """
        Subtotal: 50000
        Tax: 5000
        Total: 55000
        """
        
        result = self.parser.extract_totals(total_text)
        
        assert result["success"] is True
        assert result["subtotal"] == 50000.0
        assert result["tax"] == 5000.0
        assert result["total"] == 55000.0
    
    def test_handle_malformed_invoice(self):
        """Test handling of malformed invoice text."""
        malformed_texts = [
            "",  # Empty
            "Not an invoice",  # No structure
            "INVOICE\nCorrupted data...",  # Incomplete
        ]
        
        for text in malformed_texts:
            result = self.parser.parse_invoice_structure(text)
            assert result["success"] is False
            assert "error" in result


class TestLineParser:
    """Test suite for LineParser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = LineParser()
    
    def test_line_parser_init(self):
        """Test LineParser initialization."""
        parser = LineParser()
        
        assert parser.field_patterns is not None
        assert parser.numeric_patterns is not None
    
    def test_parse_invoice_line_standard(self):
        """Test parsing standard invoice line."""
        line_text = "Product A    2 kg    15000    30000"
        
        result = parse_invoice_line(line_text)
        
        assert result["success"] is True
        assert result["name"] == "Product A"
        assert result["qty"] == 2.0
        assert result["unit"] == "kg"
        assert result["price"] == 15000.0
        assert result["amount"] == 30000.0
    
    def test_parse_invoice_line_with_commas(self):
        """Test parsing line with comma separators."""
        line_text = "Product A, 2, kg, 15,000, 30,000"
        
        result = parse_invoice_line(line_text)
        
        assert result["success"] is True
        assert result["name"] == "Product A"
        assert result["qty"] == 2.0
        assert result["price"] == 15000.0
        assert result["amount"] == 30000.0
    
    def test_parse_invoice_line_decimal_values(self):
        """Test parsing line with decimal values."""
        line_text = "Product A    2.5 kg    15000.50    37501.25"
        
        result = parse_invoice_line(line_text)
        
        assert result["success"] is True
        assert result["qty"] == 2.5
        assert result["price"] == 15000.50
        assert result["amount"] == 37501.25
    
    def test_parse_invoice_line_missing_fields(self):
        """Test parsing line with missing fields."""
        incomplete_lines = [
            "Product A    2 kg",  # Missing price and amount
            "Product A    15000",  # Missing qty and unit
            "Product A",  # Only name
        ]
        
        for line_text in incomplete_lines:
            result = parse_invoice_line(line_text)
            assert result["success"] is True  # Should still extract what's available
            assert result["name"] == "Product A"
    
    def test_extract_line_components(self):
        """Test extracting individual line components."""
        line_text = "Fresh Tomatoes    2.5 kg    12000    30000"
        
        components = extract_line_components(line_text)
        
        assert "name" in components
        assert "quantity" in components
        assert "unit" in components
        assert "price" in components
        assert "amount" in components
    
    def test_normalize_line_data(self):
        """Test line data normalization."""
        raw_data = {
            "name": "  Product A  ",
            "qty": "2,5",
            "unit": " KG ",
            "price": "15.000",
            "amount": "37,500"
        }
        
        normalized = normalize_line_data(raw_data)
        
        assert normalized["name"] == "Product A"
        assert normalized["qty"] == 2.5
        assert normalized["unit"] == "kg"
        assert normalized["price"] == 15000.0
        assert normalized["amount"] == 37500.0
    
    def test_parse_line_with_special_characters(self):
        """Test parsing lines with special characters."""
        special_lines = [
            "Product-A/B    2 kg    15,000.50    30,001",
            "Café & Pastry    1.5 box    25000    37500",
            "Αγάπη (Love)    1 kg    10000    10000",  # Greek
        ]
        
        for line_text in special_lines:
            result = parse_invoice_line(line_text)
            assert result["success"] is True
            assert len(result["name"]) > 0
    
    def test_parse_line_different_units(self):
        """Test parsing lines with different units."""
        unit_tests = [
            ("Product A    2 kg    10000    20000", "kg"),
            ("Product B    5 pcs    5000    25000", "pcs"),
            ("Product C    1.5 liter    8000    12000", "liter"),
            ("Product D    10 gram    1000    10000", "gram"),
        ]
        
        for line_text, expected_unit in unit_tests:
            result = parse_invoice_line(line_text)
            assert result["success"] is True
            assert result["unit"] == expected_unit


class TestTextProcessor:
    """Test suite for TextProcessor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = TextProcessor()
    
    def test_text_processor_init(self):
        """Test TextProcessor initialization."""
        processor = TextProcessor()
        
        assert processor.tokenizers is not None
        assert processor.extractors is not None
    
    def test_clean_text_basic(self):
        """Test basic text cleaning."""
        dirty_text = "  This is    dirty\ttext\n\n  with   extra   spaces  "
        
        cleaned = clean_text(dirty_text)
        
        assert cleaned == "This is dirty text with extra spaces"
    
    def test_clean_text_special_characters(self):
        """Test cleaning text with special characters."""
        special_text = "Product: $pecial Ch@rs & Symbols!!! 123"
        
        cleaned = clean_text(special_text)
        
        # Should preserve readable characters
        assert "Product" in cleaned
        assert "Special" in cleaned or "$pecial" in cleaned
        assert "123" in cleaned
    
    def test_clean_text_unicode(self):
        """Test cleaning text with Unicode characters."""
        unicode_text = "Café Français Αγάπη 日本語 русский"
        
        cleaned = clean_text(unicode_text)
        
        # Should preserve Unicode characters
        assert "Café" in cleaned
        assert "Français" in cleaned
    
    def test_tokenize_text(self):
        """Test text tokenization."""
        text = "Product A costs 15000 per kg"
        
        tokens = tokenize_text(text)
        
        assert "Product" in tokens
        assert "A" in tokens
        assert "costs" in tokens
        assert "15000" in tokens
        assert "per" in tokens
        assert "kg" in tokens
    
    def test_tokenize_text_with_punctuation(self):
        """Test tokenization with punctuation."""
        text = "Invoice #123: Product A (2kg) - $15,000.50"
        
        tokens = tokenize_text(text)
        
        # Should handle punctuation appropriately
        assert "Invoice" in tokens
        assert "123" in tokens
        assert "Product" in tokens
        assert "A" in tokens
    
    def test_extract_entities_numbers(self):
        """Test extracting numeric entities."""
        text = "Product costs 15000 per kg, total 30000"
        
        entities = extract_entities(text)
        
        assert "numbers" in entities
        assert 15000 in entities["numbers"]
        assert 30000 in entities["numbers"]
    
    def test_extract_entities_currencies(self):
        """Test extracting currency entities."""
        text = "Price: $150.50, Rp 15000, €25.99"
        
        entities = extract_entities(text)
        
        assert "currencies" in entities
        currency_values = entities["currencies"]
        assert any(150.50 in str(c) for c in currency_values)
        assert any("15000" in str(c) for c in currency_values)
    
    def test_extract_entities_dates(self):
        """Test extracting date entities."""
        text = "Invoice dated 2025-05-28, due 28/06/2025"
        
        entities = extract_entities(text)
        
        assert "dates" in entities
        dates = entities["dates"]
        assert any("2025-05-28" in str(d) for d in dates)
        assert any("28/06/2025" in str(d) for d in dates)
    
    def test_normalize_whitespace(self):
        """Test whitespace normalization."""
        messy_text = "Text  with\t\tmultiple\n\n\nwhitespace\r\n   issues"
        
        normalized = normalize_whitespace(messy_text)
        
        assert normalized == "Text with multiple whitespace issues"
    
    def test_process_multilingual_text(self):
        """Test processing multilingual text."""
        multilingual_text = "Invoice фактура فاتورة 請求書 2025-05-28"
        
        processed = self.processor.process_text(multilingual_text)
        
        assert processed["success"] is True
        assert "entities" in processed
        assert "tokens" in processed
        
        # Should extract date regardless of language
        assert any("2025-05-28" in str(entity) for entity in processed["entities"]["dates"])


class TestParsersIntegration:
    """Integration tests for parser components."""
    
    def test_complete_parsing_pipeline(self):
        """Test complete parsing pipeline."""
        invoice_text = """
        INVOICE INV-2025-001
        Supplier: Test Supplier Ltd
        Date: 28.05.2025
        
        Fresh Tomatoes    2.5 kg    12000    30000
        Chicken Meat      1 kg      30000    30000
        
        Total: 60000
        """
        
        # Step 1: Text processing
        text_processor = TextProcessor()
        processed_text = text_processor.process_text(invoice_text)
        
        assert processed_text["success"] is True
        
        # Step 2: General parsing
        general_parser = GeneralParser()
        structure = general_parser.parse_invoice_structure(invoice_text)
        
        assert structure["success"] is True
        
        # Step 3: Date parsing
        date_parser = DateParser()
        date_result = date_parser.parse_date_from_text(invoice_text)
        
        assert date_result["success"] is True
        assert date_result["date"] == date(2025, 5, 28)
        
        # Step 4: Line parsing
        line_parser = LineParser()
        lines = []
        for line_text in ["Fresh Tomatoes    2.5 kg    12000    30000",
                         "Chicken Meat      1 kg      30000    30000"]:
            line_result = line_parser.parse_invoice_line(line_text)
            if line_result["success"]:
                lines.append(line_result)
        
        assert len(lines) == 2
        assert lines[0]["name"] == "Fresh Tomatoes"
        assert lines[1]["name"] == "Chicken Meat"
    
    def test_command_to_parser_integration(self):
        """Test integration between command parser and other parsers."""
        # User command to edit date
        command = "date 2025-06-01"
        
        command_parser = CommandParser()
        parsed_command = command_parser.parse_command(command)
        
        assert parsed_command["success"] is True
        assert parsed_command["command_type"] == "date"
        
        # Use date parser to validate the date
        date_parser = DateParser()
        date_result = date_parser.parse_date_from_text(parsed_command["date_value"])
        
        assert date_result["success"] is True
        assert date_result["date"] == date(2025, 6, 1)
    
    def test_error_recovery_across_parsers(self):
        """Test error recovery across different parsers."""
        problematic_text = """
        CORRUPTED INVOICE
        Supplier: 
        Date: invalid-date
        
        Malformed line without proper structure
        """
        
        # Each parser should handle errors gracefully
        text_processor = TextProcessor()
        general_parser = GeneralParser()
        date_parser = DateParser()
        line_parser = LineParser()
        
        text_result = text_processor.process_text(problematic_text)
        assert text_result["success"] is True  # Text processing should always succeed
        
        structure_result = general_parser.parse_invoice_structure(problematic_text)
        # May succeed or fail, but should not crash
        
        date_result = date_parser.parse_date_from_text(problematic_text)
        assert date_result["success"] is False  # Should detect invalid date
        
        line_result = line_parser.parse_invoice_line("Malformed line without proper structure")
        # Should extract what it can


if __name__ == "__main__":
    pytest.main([__file__])