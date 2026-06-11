"""Tests der Geschäftsmodule (CRM, Finanzen, HR, Projekte, Wissen)."""


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_crm_crud(client):
    created = client.post("/api/crm/customers", json={"name": "Testkunde AG", "status": "lead"})
    assert created.status_code == 201
    customer_id = created.json()["id"]

    updated = client.patch(f"/api/crm/customers/{customer_id}", json={"status": "aktiv"})
    assert updated.json()["status"] == "aktiv"

    interaction = client.post(
        f"/api/crm/customers/{customer_id}/interactions",
        json={"kind": "anruf", "summary": "Erstgespräch geführt"},
    )
    assert interaction.status_code == 201

    detail = client.get(f"/api/crm/customers/{customer_id}")
    assert len(detail.json()["interactions"]) == 1

    assert client.delete(f"/api/crm/customers/{customer_id}").status_code == 204
    assert client.get(f"/api/crm/customers/{customer_id}").status_code == 404


def test_finance_invoices_and_gross_amount(client):
    invoice = client.post("/api/finance/invoices", json={
        "number": "RE-001", "amount_net": 100.0, "vat_rate": 19.0, "issue_date": "2026-06-01",
    })
    assert invoice.status_code == 201
    assert invoice.json()["amount_gross"] == 119.0

    duplicate = client.post("/api/finance/invoices", json={
        "number": "RE-001", "amount_net": 50.0, "issue_date": "2026-06-02",
    })
    assert duplicate.status_code == 409


def test_hr_absence_validation(client):
    employee = client.post("/api/hr/employees", json={"first_name": "Max", "last_name": "Muster"})
    employee_id = employee.json()["id"]

    invalid = client.post(f"/api/hr/employees/{employee_id}/absences", json={
        "kind": "urlaub", "start_date": "2026-07-10", "end_date": "2026-07-01",
    })
    assert invalid.status_code == 422

    valid = client.post(f"/api/hr/employees/{employee_id}/absences", json={
        "kind": "urlaub", "start_date": "2026-07-01", "end_date": "2026-07-10",
    })
    assert valid.status_code == 201


def test_projects_and_tasks(client):
    project = client.post("/api/projects", json={"name": "Website-Relaunch", "budget": 15000})
    project_id = project.json()["id"]

    task = client.post(f"/api/projects/{project_id}/tasks", json={"title": "Konzept erstellen"})
    task_id = task.json()["id"]

    done = client.patch(f"/api/projects/tasks/{task_id}", json={"status": "erledigt"})
    assert done.json()["status"] == "erledigt"


def test_knowledge_versioning(client):
    doc = client.post("/api/knowledge/documents", json={
        "title": "SOP: Test", "doc_type": "sop", "content": "Schritt 1. Schritt 2.",
    })
    assert doc.status_code == 201
    doc_id = doc.json()["id"]
    assert doc.json()["version"] == 1

    updated = client.patch(f"/api/knowledge/documents/{doc_id}", json={"content": "Schritt 1 neu."})
    assert updated.json()["version"] == 2

    invalid_type = client.post("/api/knowledge/documents", json={
        "title": "X", "doc_type": "unbekannt", "content": "…",
    })
    assert invalid_type.status_code == 422
