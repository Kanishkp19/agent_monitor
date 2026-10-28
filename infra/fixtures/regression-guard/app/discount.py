def shipping_fee(subtotal: int) -> int:
    if subtotal > 50:
        return 0
    return 5
