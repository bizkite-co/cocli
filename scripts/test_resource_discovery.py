from cocli.scrapers.resource_analyzer import analyze_resource_value

def test_resource_analyzer() -> None:
    # Test public facility
    res1 = analyze_resource_value("Fullerton Public Library", "Public library", "Free books and study space.", "Great free resource!")
    print(f"Library: {res1}")
    assert res1["is_value_resource"] is True
    assert res1["fee_category"] == "free_or_nominal"

    # Test nominal fee
    res2 = analyze_resource_value("Fullerton Museum", "Museum", "History of Fullerton. $5 entrance fee.", "Cool local museum.")
    print(f"Museum: {res2}")
    assert res2["is_value_resource"] is True
    assert res2["fee_category"] == "nominal"

    # Test subscription/commercial
    res3 = analyze_resource_value("24 Hour Fitness", "Gym", "Monthly membership required.", "Expensive but good.")
    print(f"Gym: {res3}")
    assert res3["is_value_resource"] is False
    assert res3["fee_category"] == "subscription"

    print("All Resource Analyzer tests passed!")

if __name__ == "__main__":
    test_resource_analyzer()
