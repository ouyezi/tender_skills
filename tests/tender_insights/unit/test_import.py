def test_package_importable():
    import tender_insights

    assert tender_insights.__version__ == "0.1.0"
