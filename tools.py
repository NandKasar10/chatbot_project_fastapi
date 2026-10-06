def get_stock_price(company : str) -> int :
    """Returns the stock price of company mentioned.
    
    Args:
        company : The Name of the company, e.g. TCS, Microsoft, Google etc.
    """

    if company.lower() == "tcs":
        return 3500
    if company.lower() == "microsoft":
        return 5000
    if company.lower() == "google":
        return 5500
    if company.lower() == "rungta":
        return 7000
    
    return 0