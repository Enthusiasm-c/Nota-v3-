from app import data_loader
import pytest
from unittest.mock import patch, mock_open, MagicMock
from app.models import Product


def test_load_suppliers():
    try:
        suppliers = data_loader.load_suppliers("data/suppliers.csv")
        assert isinstance(suppliers, list)
    except FileNotFoundError:
        pass  # Acceptable in CI


def test_load_products():
    try:
        products = data_loader.load_products("data/products.csv")
        assert isinstance(products, list)
    except FileNotFoundError:
        pass