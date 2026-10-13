"""Covers the private, sensitive document upload/review flow for contracts:
required document types differ for private vs. company customers, a document
goes through PENDING_REVIEW -> APPROVED/REJECTED, and the presigned URL
mechanism never returns a public/guessable link."""

import uuid

import pytest

from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.documents import service as documents_service
from app.domains.network import service as network_service
from tests.test_commission_engine_integration import _make_actor


async def _make_customer_and_supply_point(db, organization_id, *, kind="PRIVATE"):
    customer = Customer(organization_id=organization_id, kind=kind, email=f"doc-{uuid.uuid4().hex[:8]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Documenti 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)
    await db.commit()
    return customer, supply_point


async def _make_contract(db, organization_id, *, customer_kind="PRIVATE"):
    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id, kind=customer_kind)

    product = Product(organization_id=organization_id, code=f"DOC-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    from app.core.db import utcnow

    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test document product", base_price_cents=1000,
        contract_duration_months=12, valid_from=utcnow(),
    )
    db.add(product_version)
    await db.commit()

    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Doc", last_name="Agent",
        promoter_code=f"DA-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=agent.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    return contract, customer, actor_user_id


def test_required_document_types_for_private_customer():
    types = documents_service.required_document_types_for("PRIVATE")
    assert set(types) == {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL"}
    assert "CHAMBER_OF_COMMERCE" not in types


def test_required_document_types_for_company_customer():
    types = documents_service.required_document_types_for("COMPANY")
    assert "CHAMBER_OF_COMMERCE" in types
    assert set(types) == {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE"}


def test_a_partita_iva_must_give_its_visura_or_its_p_iva_certificate():
    """Session 82: every partita IVA proves it. The one slot takes either the
    visura camerale (a company, a ditta) or the certificato di attribuzione
    della partita IVA (a libero professionista, who has no visura)."""
    slots = {s.document_type: s.required for s in documents_service.document_slots_for("SOLE_PROPRIETOR")}
    assert slots["CHAMBER_OF_COMMERCE"] is True
    assert "CHAMBER_OF_COMMERCE" in documents_service.required_document_types_for("SOLE_PROPRIETOR")


def test_a_private_customer_is_not_even_offered_the_visura():
    slots = [s.document_type for s in documents_service.document_slots_for("PRIVATE")]
    assert "CHAMBER_OF_COMMERCE" not in slots


# --- Allegati aggiuntivi -------------------------------------------------


@pytest.mark.asyncio
async def test_an_extra_attachment_must_say_what_it_is(db, organization_id):
    """The whole point of the open slot is that somebody names the thing --
    an unlabelled "Documento aggiuntivo" is no better than no slot at all."""
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    for bad in (None, "", "   ", "ok"):
        with pytest.raises(documents_service.DocumentValidationError):
            await documents_service.upload_document(
                db, organization_id=organization_id, contract_id=contract.id, document_type="OTHER",
                description=bad, file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
                original_filename="x.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
            )


@pytest.mark.asyncio
async def test_an_extra_attachment_keeps_a_tidied_up_version_of_its_label(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="OTHER",
        description="  Delega    firmata\n", file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
        original_filename="delega.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    assert document.description == "Delega firmata"


@pytest.mark.asyncio
async def test_a_label_longer_than_the_column_is_refused_rather_than_truncated(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    with pytest.raises(documents_service.DocumentValidationError):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type="OTHER",
            description="x" * 121, file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
            original_filename="x.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
        )


@pytest.mark.asyncio
async def test_a_slot_document_can_never_relabel_itself(db, organization_id):
    """Accepting a caller-supplied label on IDENTITY would let a document
    arrive in the identity slot calling itself something else."""
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        description="In realtà è la bolletta", file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    assert document.description is None


@pytest.mark.asyncio
async def test_extra_attachments_accumulate_instead_of_replacing_each_other(db, organization_id):
    """A second identity document supersedes the first; a second attachment
    is a second attachment."""
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    for label in ("Carta d'identità retro", "Contratto di locazione"):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type="OTHER",
            description=label, file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
            original_filename="x.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
        )

    extra = await documents_service.get_extra_documents_for_contract(
        db, organization_id=organization_id, contract=contract, customer_kind="PRIVATE"
    )
    assert [d.description for d in extra] == ["Carta d'identità retro", "Contratto di locazione"]

    rows = await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind="PRIVATE"
    )
    assert all(row["document"] is None for row in rows), "un allegato extra non riempie una casella richiesta"


@pytest.mark.asyncio
async def test_a_document_whose_slot_disappeared_is_still_shown(db, organization_id):
    """A visura uploaded while the customer was registered as a company must
    not silently vanish from the screen if they are later corrected to
    PRIVATE -- the file is still in the bucket either way."""
    contract, customer, actor_user_id = await _make_contract(db, organization_id, customer_kind="COMPANY")
    await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="CHAMBER_OF_COMMERCE",
        file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
        original_filename="visura.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    extra = await documents_service.get_extra_documents_for_contract(
        db, organization_id=organization_id, contract=contract, customer_kind="PRIVATE"
    )
    assert [d.document_type for d in extra] == ["CHAMBER_OF_COMMERCE"]


@pytest.mark.asyncio
async def test_an_extra_attachment_does_not_hold_the_contract_back(db, organization_id):
    """An extra attachment never sends a contract to review by itself; the
    required documents -- visura / P.IVA included for a ditta -- do."""
    contract, customer, actor_user_id = await _make_contract(db, organization_id, customer_kind="SOLE_PROPRIETOR")
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="SUBMITTED",
        actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )

    await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="OTHER",
        description="Contratto di locazione", file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
        original_filename="x.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    refreshed = await db.get(type(contract), contract.id)
    assert refreshed.status == "SUBMITTED", "un allegato extra da solo non manda nulla in revisione"

    for doc_type in documents_service.required_document_types_for("SOLE_PROPRIETOR"):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type=doc_type,
            file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
            original_filename=f"{doc_type}.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
        )

    refreshed = await db.get(type(contract), contract.id)
    assert refreshed.status == "UNDER_REVIEW"


@pytest.mark.asyncio
async def test_upload_document_and_read_back(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)

    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"%PDF-1.4\nfake pdf bytes for a test", content_type="application/pdf",
        original_filename="carta_identita.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    assert document.status == "PENDING_REVIEW"
    assert document.document_type == "IDENTITY"
    assert document.storage_key.startswith(f"documents/{contract.id}/")

    docs = await documents_service.list_documents_for_contract(
        db, organization_id=organization_id, contract_id=contract.id
    )
    assert len(docs) == 1
    assert docs[0].id == document.id


@pytest.mark.asyncio
async def test_upload_document_rejects_unknown_document_type(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    with pytest.raises(documents_service.DocumentValidationError):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type="NOT_A_REAL_TYPE",
            file_bytes=b"%PDF-1.4\nirrelevant", content_type="application/pdf",
            original_filename="x.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
        )


@pytest.mark.asyncio
async def test_contract_documents_status_shows_missing_and_uploaded(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id, customer_kind="COMPANY")

    await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"%PDF-1.4\nid bytes", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )

    rows = await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind="COMPANY"
    )
    by_type = {r["document_type"]: r["document"] for r in rows}
    assert set(by_type.keys()) == {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE"}
    assert by_type["IDENTITY"] is not None
    assert by_type["FISCAL_CODE"] is None
    assert by_type["CHAMBER_OF_COMMERCE"] is None


@pytest.mark.asyncio
async def test_review_document_approve_and_reject(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    admin_user_id = await _make_actor(db, organization_id)

    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="UTILITY_BILL",
        file_bytes=b"\xff\xd8\xffbill bytes", content_type="image/jpeg",
        original_filename="bolletta.jpg", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )

    approved = await documents_service.review_document(
        db, organization_id=organization_id, document_id=document.id, new_status="APPROVED",
        review_note="Documento chiaro e leggibile", actor_user_id=admin_user_id,
    )
    assert approved.status == "APPROVED"
    assert approved.reviewed_by_user_id == admin_user_id
    assert approved.reviewed_at is not None

    rejected = await documents_service.review_document(
        db, organization_id=organization_id, document_id=document.id, new_status="REJECTED",
        review_note="In realtà è sfocato, richiedine uno nuovo", actor_user_id=admin_user_id,
    )
    assert rejected.status == "REJECTED"
    assert rejected.review_note == "In realtà è sfocato, richiedine uno nuovo"


@pytest.mark.asyncio
async def test_presigned_document_url_is_time_limited_and_not_the_internal_endpoint(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"%PDF-1.4\nsensitive id document bytes", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )

    url = await documents_service.get_presigned_url_for_document(document)
    # never the raw internal docker-network address -- that would be
    # unreachable from a browser AND would leak infrastructure details
    assert "minio:9000" not in url
    assert "X-Amz-Signature" in url or "X-Amz-Expires" in url
    assert document.storage_key in url


@pytest.mark.asyncio
async def test_get_document_returns_none_for_wrong_organization(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    other_org_id = uuid.uuid4()
    result = await documents_service.get_document(db, organization_id=other_org_id, document_id=document.id)
    assert result is None


# --- Pagine di un documento (Session 82) -----------------------------------


@pytest.mark.asyncio
async def test_a_document_has_pages_up_to_twenty_and_a_page_can_be_taken_out(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)

    async def page(n):
        return await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type="UTILITY_BILL",
            file_bytes=b"%PDF-1.4\nx", content_type="application/pdf",
            original_filename=f"bolletta-{n}.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
        )

    first = await page(1)
    for n in range(2, documents_service.MAX_PAGES_PER_DOCUMENT + 1):
        await page(n)
    with pytest.raises(documents_service.DocumentValidationError, match="20 pagine"):
        await page(21)

    rows = await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind="PRIVATE"
    )
    bill = next(r for r in rows if r["document_type"] == "UTILITY_BILL")
    assert [d.original_filename for d in bill["pages"]][:2] == ["bolletta-1.pdf", "bolletta-2.pdf"]
    assert len(bill["pages"]) == 20
    assert bill["document"].original_filename == "bolletta-20.pdf"

    await documents_service.delete_document(db, document=first, actor_user_id=actor_user_id)
    await page(21)  # a page freed, one more fits

    approved = bill["pages"][1]
    await documents_service.review_document(
        db, organization_id=organization_id, document_id=approved.id, new_status="APPROVED",
        review_note=None, actor_user_id=actor_user_id,
    )
    with pytest.raises(documents_service.DocumentDeletionError):
        await documents_service.delete_document(db, document=approved, actor_user_id=actor_user_id)
