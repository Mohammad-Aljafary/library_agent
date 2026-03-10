from sqlalchemy import (create_engine, Column, Integer, String, DateTime, ForeignKey, Text)
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from sqlalchemy.sql import func
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_HOST", "sqlite:///./db/library.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

class Base(DeclarativeBase):
    pass

class Books(Base):
    __tablename__ = 'books'
    isbn = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False, default=0)
    stock = Column(Integer, nullable=False, default=0)
    orders = relationship("Orders", back_populates="book")
    order_items = relationship("OrderItems", back_populates="book")

class Customers(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    orders = relationship("Orders", back_populates="customer")

class Orders(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    book_isbn = Column(String, ForeignKey('books.isbn'), nullable=False)
    order_date = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customers", back_populates="orders")
    book = relationship("Books", back_populates="orders")
    items = relationship("OrderItems", back_populates="order")

class OrderItems(Base):
    __tablename__ = 'order_items'
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    book_isbn = Column(String, ForeignKey('books.isbn'), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("Orders", back_populates="items")
    book = relationship("Books", back_populates="order_items")

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    session_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ToolCall(Base):
    __tablename__ = 'tool_calls'
    id = Column(Integer, primary_key=True)
    session_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    args_json = Column(Text, nullable=False)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

def get_session():
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()

def init_db():
    """create tables in the database"""
    os.makedirs("db", exist_ok=True)
    Base.metadata.create_all(engine)
    print("Database initialized.")