from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate

router = APIRouter(prefix="/api", tags=["customers"])


@router.get("/customers", response_model=list[CustomerRead])
def list_customers(db: Session = Depends(get_db)) -> list[CustomerRead]:
    repository = CustomerRepository(db)
    return repository.list()


@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerRead:
    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> CustomerRead:
    repository = CustomerRepository(db)
    return repository.create(payload)


@router.put("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)) -> CustomerRead:
    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return repository.update(customer, payload)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> None:
    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    repository.delete(customer)
