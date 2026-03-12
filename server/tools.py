import json
import logging
from sqlalchemy.orm import Session
from langchain_core.tools import tool
from db.tables import Books, Customers, Orders, OrderItems, ToolCall
from server.tool_validator import ToolCallValidator

logger = logging.getLogger(__name__)

# Module-level reference set by the agent before each invocation.
# The validator is stored here so every tool can access it without
# changing the LangChain @tool function signatures.
_active_validator: ToolCallValidator | None = None


def set_active_validator(validator: ToolCallValidator | None):
    """Called by the agent layer to install the current request's validator."""
    global _active_validator
    _active_validator = validator


def make_tools(db: Session, session_id: str):
    """Create all agent tools bound to the given DB session and chat session."""

    def log_tool_call(name: str, args: dict, result: dict):
        tc = ToolCall(
            session_id=session_id,
            name=name,
            args_json=json.dumps(args),
            result_json=json.dumps(result),
        )
        db.add(tc)

    def _guard(tool_name: str) -> str | None:
        """Return an error string if the validator blocks *tool_name*, else None."""
        if _active_validator is None:
            return None
        ok, reason = _active_validator.validate(tool_name)
        if not ok:
            log_tool_call(tool_name, {"_blocked": True}, {"error": reason})
            db.commit()
            return reason
        return None

    @tool
    def find_books(q: str, by: str = "title") -> list:
        """Search for books by title or author.
        Args:
            q: search query string
            by: search field - either 'title' or 'author'
        """
        if by == "author":
            results = db.query(Books).filter(Books.author.ilike(f"%{q}%")).all()
        else:
            results = db.query(Books).filter(Books.title.ilike(f"%{q}%")).all()

        data = [
            {"isbn": b.isbn, "title": b.title, "author": b.author,
             "year": b.year, "price": b.price, "stock": b.stock}
            for b in results
        ]
        log_tool_call("find_books", {"q": q, "by": by}, data)
        db.commit()
        return data

    @tool
    def create_order(customer_id: int, items: list) -> dict:
        """Create a new order for a customer and reduce stock.
        Args:
            customer_id: the customer's ID
            items: list of dicts with 'isbn' and 'qty' keys, e.g. [{"isbn": "978-...", "qty": 2}]
        """
        blocked = _guard("create_order")
        if blocked:
            return {"error": blocked}

        customer = db.query(Customers).filter(Customers.id == customer_id).first()
        if not customer:
            return {"error": f"Customer {customer_id} not found"}

        result_items = []
        for item in items:
            book = db.query(Books).filter(Books.isbn == item["isbn"]).first()
            if not book:
                return {"error": f"Book with ISBN {item['isbn']} not found"}
            if book.stock < item["qty"]:
                return {"error": f"Insufficient stock for '{book.title}' (have {book.stock}, need {item['qty']})"}

        # All checks passed — create the order
        order = Orders(customer_id=customer_id, book_isbn=items[0]["isbn"])
        db.add(order)
        db.flush()

        for item in items:
            book = db.query(Books).filter(Books.isbn == item["isbn"]).first()
            book.stock -= item["qty"]
            db.add(OrderItems(
                order_id=order.id,
                book_isbn=book.isbn,
                quantity=item["qty"],
            ))
            result_items.append({
                "title": book.title,
                "isbn": book.isbn,
                "qty": item["qty"],
                "new_stock": book.stock,
            })

        db.flush()
        result = {"order_id": order.id, "customer": customer.name, "items": result_items}
        log_tool_call("create_order", {"customer_id": customer_id, "items": items}, result)
        db.commit()
        return result

    @tool
    def restock_book(isbn: str, qty: int) -> dict:
        """Add stock to a book by its ISBN.
        Args:
            isbn: the book's ISBN
            qty: number of copies to add
        """
        blocked = _guard("restock_book")
        if blocked:
            return {"error": blocked}

        book = db.query(Books).filter(Books.isbn == isbn).first()
        if not book:
            return {"error": f"Book with ISBN {isbn} not found"}
        book.stock += qty
        db.flush()
        result = {"isbn": isbn, "title": book.title, "new_stock": book.stock}
        log_tool_call("restock_book", {"isbn": isbn, "qty": qty}, result)
        db.commit()
        return result

    @tool
    def update_price(isbn: str, price: float) -> dict:
        """Update the price of a book.
        Args:
            isbn: the book's ISBN
            price: the new price
        """
        blocked = _guard("update_price")
        if blocked:
            return {"error": blocked}

        book = db.query(Books).filter(Books.isbn == isbn).first()
        if not book:
            return {"error": f"Book with ISBN {isbn} not found"}
        book.price = price
        db.flush()
        result = {"isbn": isbn, "title": book.title, "new_price": book.price}
        log_tool_call("update_price", {"isbn": isbn, "price": price}, result)
        db.commit()
        return result

    @tool
    def add_to_order(order_id: int, items: list) -> dict:
        """Add items to an existing order and reduce stock.
        Args:
            order_id: the order ID to add items to
            items: list of dicts with 'isbn' and 'qty' keys, e.g. [{"isbn": "978-...", "qty": 1}]
        """
        blocked = _guard("add_to_order")
        if blocked:
            return {"error": blocked}

        order = db.query(Orders).filter(Orders.id == order_id).first()
        if not order:
            return {"error": f"Order {order_id} not found"}

        result_items = []
        for item in items:
            book = db.query(Books).filter(Books.isbn == item["isbn"]).first()
            if not book:
                return {"error": f"Book with ISBN {item['isbn']} not found"}
            if book.stock < item["qty"]:
                return {"error": f"Insufficient stock for '{book.title}' (have {book.stock}, need {item['qty']})"}

        # All checks passed — add the items
        for item in items:
            book = db.query(Books).filter(Books.isbn == item["isbn"]).first()
            book.stock -= item["qty"]
            db.add(OrderItems(
                order_id=order.id,
                book_isbn=book.isbn,
                quantity=item["qty"],
            ))
            result_items.append({
                "title": book.title,
                "isbn": book.isbn,
                "qty": item["qty"],
                "new_stock": book.stock,
            })

        db.flush()
        result = {
            "order_id": order.id,
            "customer": order.customer.name,
            "added_items": result_items
        }
        log_tool_call("add_to_order", {"order_id": order_id, "items": items}, result)
        db.commit()
        return result

    @tool
    def order_status(order_id: int) -> dict:
        """Get the status and details of an order by its ID.
        Args:
            order_id: the order ID to look up
        """
        order = db.query(Orders).filter(Orders.id == order_id).first()
        if not order:
            return {"error": f"Order {order_id} not found"}

        items = [
            {"title": i.book.title, "isbn": i.book_isbn,
             "qty": i.quantity}
            for i in order.items
        ]
        result = {
            "order_id": order.id,
            "customer": order.customer.name,
            "book": order.book.title,
            "created_at": str(order.order_date),
            "items": items,
        }
        log_tool_call("order_status", {"order_id": order_id}, result)
        db.commit()
        return result

    @tool
    def inventory_summary() -> dict:
        """Get a summary of the full inventory including total books, total stock, and low-stock titles (stock < 5)."""
        books = db.query(Books).all()
        total_stock = sum(b.stock for b in books)
        low_stock = [
            {"isbn": b.isbn, "title": b.title, "author": b.author, "stock": b.stock}
            for b in books if b.stock < 5
        ]
        result = {
            "total_titles": len(books),
            "total_stock": total_stock,
            "low_stock_titles": low_stock,
        }
        log_tool_call("inventory_summary", {}, result)
        db.commit()
        return result

    @tool
    def list_orders() -> list:
        """Get a list of all orders with their items and details."""
        orders = db.query(Orders).all()
        result = []
        for order in orders:
            items = [
                {
                    "title": item.book.title,
                    "isbn": item.book_isbn,
                    "quantity": item.quantity,
                    "price": item.book.price
                }
                for item in order.items
            ]
            result.append({
                "order_id": order.id,
                "customer": order.customer.name,
                "order_date": str(order.order_date),
                "items": items,
                "total_items": len(items)
            })
        log_tool_call("list_orders", {}, result)
        db.commit()
        return result

    return [find_books, create_order, add_to_order, restock_book, update_price, order_status, list_orders, inventory_summary]
