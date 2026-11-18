from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

import pandas as pd


CDISC_DOMAIN_HINTS: dict[str, str] = {
    "participant_id": "DM",
    "subject_id": "DM",
    "sex": "DM",
    "age": "DM",
    "race": "DM",
    "ethnicity": "DM",
    "adverse_event": "AE",
    "medication": "CM",
    "lab_test": "LB",
    "lab_value": "LB",
    "vital_sign": "VS",
    "exposure": "EX",
    "disposition": "DS",
    "medical_history": "MH",
    "questionnaire": "QS",
    "tumor_response": "RS",
}

FHIR_RESOURCE_HINTS: dict[str, str] = {
    "participant_id": "Patient.identifier",
    "sex": "Patient.gender",
    "birth_date": "Patient.birthDate",
    "condition": "Condition.code",
    "medication": "MedicationStatement.medication",
    "lab_test": "Observation.code",
    "lab_value": "Observation.value[x]",
    "visit_date": "Encounter.period",
    "procedure": "Procedure.code",
    "consent": "Consent.status",
}


def build_variable_mapping(variables: pd.DataFrame) -> pd.DataFrame:
    required = {"variable", "label", "data_type"}
    missing = sorted(required - set(variables.columns))
    if missing:
        raise ValueError("Variable dictionary is missing: " + ", ".join(missing))
    rows: list[dict[str, Any]] = []
    for _, row in variables.iterrows():
        name = str(row["variable"]).strip()
        normalized = name.casefold()
        domain = str(row.get("sdtm_domain") or CDISC_DOMAIN_HINTS.get(normalized, "SUPP"))
        fhir = str(row.get("fhir_path") or FHIR_RESOURCE_HINTS.get(normalized, "QuestionnaireResponse.item.answer"))
        role = str(row.get("analysis_role") or "Covariate")
        rows.append(
            {
                "variable": name,
                "label": str(row["label"]),
                "data_type": str(row["data_type"]),
                "unit": str(row.get("unit", "")),
                "codelist": str(row.get("codelist", "")),
                "cdash_variable": str(row.get("cdash_variable") or name.upper()),
                "sdtm_domain": domain.upper(),
                "adam_dataset": str(row.get("adam_dataset") or "ADSL"),
                "analysis_role": role,
                "derivation": str(row.get("derivation", "Source")),
                "fhir_path": fhir,
                "source_provenance": str(row.get("source_provenance", "Planned CRF")),
                "status": "Mapped" if domain and fhir else "Needs review",
            }
        )
    return pd.DataFrame(rows)


def build_fhir_questionnaire(mapping: pd.DataFrame, title: str = "BioIntel Research CRF") -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    type_map = {"integer": "integer", "float": "decimal", "number": "decimal", "date": "date", "datetime": "dateTime", "boolean": "boolean"}
    for _, row in mapping.iterrows():
        raw_type = str(row.get("data_type", "string")).casefold()
        items.append(
            {
                "linkId": str(row["variable"]),
                "text": str(row["label"]),
                "type": type_map.get(raw_type, "string"),
                "required": bool(row.get("required", False)),
                "extension": [
                    {"url": "https://biointel.local/fhir/source-path", "valueString": str(row.get("fhir_path", ""))},
                    {"url": "https://biointel.local/fhir/unit", "valueString": str(row.get("unit", ""))},
                ],
            }
        )
    payload = {
        "resourceType": "Questionnaire",
        "status": "draft",
        "title": title,
        "item": items,
        "meta": {"tag": [{"system": "https://biointel.local", "code": "research-planning"}]},
    }
    payload["identifier"] = [{"system": "urn:sha256", "value": sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}]
    return payload


def build_odm_xml(mapping: pd.DataFrame, study_oid: str = "BIOINTEL.STUDY") -> bytes:
    root = Element("ODM", {"ODMVersion": "1.3.2", "FileType": "Snapshot", "Originator": "BioIntel AI"})
    study = SubElement(root, "Study", {"OID": study_oid})
    globals_ = SubElement(study, "GlobalVariables")
    SubElement(globals_, "StudyName").text = study_oid
    SubElement(globals_, "StudyDescription").text = "BioIntel machine-readable research planning export"
    SubElement(globals_, "ProtocolName").text = study_oid
    metadata = SubElement(study, "MetaDataVersion", {"OID": "MDV.1", "Name": "BioIntel Planning Metadata"})
    item_group = SubElement(metadata, "ItemGroupDef", {"OID": "IG.CRF", "Name": "Research CRF", "Repeating": "Yes"})
    for index, row in mapping.reset_index(drop=True).iterrows():
        oid = f"IT.{str(row['variable']).upper()}"
        SubElement(item_group, "ItemRef", {"ItemOID": oid, "OrderNumber": str(index + 1), "Mandatory": "No"})
        item = SubElement(metadata, "ItemDef", {"OID": oid, "Name": str(row["label"]), "DataType": "text"})
        description = SubElement(item, "Description")
        SubElement(description, "TranslatedText", {"xml:lang": "en"}).text = str(row["label"])
    return tostring(root, encoding="utf-8", xml_declaration=True)


def build_define_xml_readiness(mapping: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("Variable names unique", mapping["variable"].astype(str).is_unique),
        ("Labels complete", mapping["label"].astype(str).str.strip().ne("").all()),
        ("SDTM domains assigned", mapping["sdtm_domain"].astype(str).str.strip().ne("").all()),
        ("ADaM datasets assigned", mapping["adam_dataset"].astype(str).str.strip().ne("").all()),
        ("Analysis roles assigned", mapping["analysis_role"].astype(str).str.strip().ne("").all()),
        ("Derivations documented", mapping["derivation"].astype(str).str.strip().ne("").all()),
        ("FHIR source paths assigned", mapping["fhir_path"].astype(str).str.strip().ne("").all()),
    ]
    return pd.DataFrame([{"check": name, "status": "Ready" if passed else "Needs review"} for name, passed in checks])
