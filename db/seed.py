import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from db.tables import engine, init_db, Books, Customers, Orders
from sqlalchemy.orm import Session

def seed_data():
    init_db()  # Ensure tables are created

    with Session(engine) as db:

        if db.query(Books).first():
            print("Data already seeded, skipping.")
            return

        # Seed books
        book_list = [
            Books(isbn="978-0132350884", title="Clean Code", author="Robert C. Martin", year=2008, price=35, stock=10),
            Books(isbn="978-0201616224", title="The Pragmatic Programmer", author="Andrew Hunt and David Thomas", year=1999, price=40, stock=8),
            Books(isbn="978-0131103627", title="The C Programming Language", author="Brian W. Kernighan and Dennis M. Ritchie", year=1988, price=30, stock=5),
            Books(isbn="978-1491950296", title="Fluent Python", author="Luciano Ramalho", year=2015, price=45, stock=12),
            Books(isbn="978-0062350615", title="The Art of Computer Programming", author="Donald E. Knuth", year=1968, price=50, stock=3),
            Books(isbn="978-0134685991", title="The Clean Coder", author="Robert C. Martin", year=2011, price=32, stock=7),
            Books(isbn="978-0132356139", title="Clean Architecture", author="Robert C. Martin", year=2017, price=38, stock=6),
        ]
        db.add_all(book_list)
        db.commit()

        # Seed customers
        customer_list = [
            Customers(name="John Doe",    email="john.doe@example.com"),
            Customers(name="Jane Smith",  email="jane.smith@example.com"),
            Customers(name="Bob Johnson", email="bob.johnson@example.com"),
        ]
        db.add_all(customer_list)
        db.commit()

        # Seed orders
        order_list = [
            Orders(customer_id=1, book_isbn="978-0132350884"),
            Orders(customer_id=1, book_isbn="978-0201616224"),
            Orders(customer_id=2, book_isbn="978-0131103627"),
            Orders(customer_id=3, book_isbn="978-1491950296"),
        ]
        db.add_all(order_list)
        db.commit()

        print("Data seeded successfully.")

if __name__ == "__main__":
    seed_data()