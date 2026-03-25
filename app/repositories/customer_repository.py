from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerSelfUpdate, CustomerUpdate


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[Customer]:
        return list(self.db.scalars(select(Customer).order_by(Customer.id)))

    def get(self, customer_id: int) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def get_by_email(self, email: str) -> Customer | None:
        return self.db.scalar(select(Customer).where(Customer.email == email))

    def create(self, payload: CustomerCreate, password_hash: str | None = None) -> Customer:
        customer_id = None
        if self.db.get_bind().dialect.name == "sqlite":
            customer_id = int(self.db.scalar(select(func.coalesce(func.max(Customer.id), 0) + 1)) or 1)
        customer = Customer(
            id=customer_id,
            name=payload.name,
            email=payload.email,
            password_hash=password_hash,
            address_line1=payload.address_line1,
            city=payload.city,
            postal_code=payload.postal_code,
            country=payload.country,
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer: Customer, payload: CustomerUpdate | CustomerSelfUpdate) -> Customer:
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(customer, field, value)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def delete(self, customer: Customer) -> None:
        self.db.delete(customer)
        self.db.commit()
