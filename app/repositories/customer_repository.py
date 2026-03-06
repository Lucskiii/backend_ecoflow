from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[Customer]:
        return list(self.db.scalars(select(Customer).order_by(Customer.id)))

    def get(self, customer_id: int) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def create(self, payload: CustomerCreate) -> Customer:
        customer = Customer(name=payload.name, email=payload.email)
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer: Customer, payload: CustomerUpdate) -> Customer:
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(customer, field, value)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def delete(self, customer: Customer) -> None:
        self.db.delete(customer)
        self.db.commit()
