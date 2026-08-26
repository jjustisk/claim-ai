"""HTML for the Allianz motor / property claim form used by the test portal."""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any

from app.services.claim_form import (
    BUILDING_AREAS,
    CONTENTS_CATEGORIES,
    CONTACT_METHODS,
    INSURANCE_TYPES,
    MOTOR_RELATIONSHIPS,
    PROPERTY_CLAIM_TYPES,
    PROPERTY_RELATIONSHIPS,
    STATES,
    TITLES,
    VEHICLE_DAMAGE_AREAS,
    VEHICLE_TYPES,
    policy_matches_insurance_type,
)


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _date_input(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _selected(current: Any, value: str) -> str:
    return "selected" if str(current or "") == value else ""


def _checked(current: Any, value: str | bool) -> str:
    if isinstance(value, bool):
        return "checked" if current is value else ""
    if isinstance(current, list):
        return "checked" if value in current else ""
    return "checked" if str(current or "") == str(value) else ""


def _hidden(show: bool) -> str:
    return "" if show else "hidden"


def _select(name: str, options: tuple[str, ...] | tuple[tuple[str, str], ...], current: Any, *, required: bool = False, blank: str = "Select") -> str:
    req = "required" if required else ""
    items = [f'<option value="">{html.escape(blank)}</option>']
    for option in options:
        if isinstance(option, tuple):
            value, label = option
        else:
            value = label = option
        items.append(
            f'<option value="{html.escape(value)}" {_selected(current, value)}>{html.escape(label)}</option>'
        )
    return f'<select id="{html.escape(name)}" name="{html.escape(name)}" {req}>{"".join(items)}</select>'


def _input(name: str, current: Any, *, required: bool = False, kind: str = "text", placeholder: str = "") -> str:
    req = "required" if required else ""
    ph = f'placeholder="{html.escape(placeholder)}"' if placeholder else ""
    value = _date_input(current) if kind == "date" else current
    return (
        f'<input id="{html.escape(name)}" name="{html.escape(name)}" type="{kind}" '
        f'value="{_esc(value)}" {req} {ph}>'
    )


def _textarea(name: str, current: Any, *, required: bool = False, placeholder: str = "") -> str:
    req = "required" if required else ""
    ph = f'placeholder="{html.escape(placeholder)}"' if placeholder else ""
    return (
        f'<textarea id="{html.escape(name)}" name="{html.escape(name)}" maxlength="8000" {req} {ph}>'
        f"{html.escape(str(current or ''))}</textarea>"
    )


def _yes_no(name: str, current: Any, *, required: bool = False) -> str:
    req = "required" if required else ""
    return f"""
      <div class="choice">
        <label><input type="radio" name="{html.escape(name)}" value="yes" {_checked(current, True)} {req}> Yes</label>
        <label><input type="radio" name="{html.escape(name)}" value="no" {_checked(current, False)}> No</label>
      </div>
    """


def _checks(name: str, options: tuple[str, ...], current: Any) -> str:
    selected = current if isinstance(current, list) else [part.strip() for part in str(current or "").split(",") if part.strip()]
    boxes = []
    for option in options:
        boxes.append(
            f'<label><input type="checkbox" name="{html.escape(name)}" value="{html.escape(option)}" '
            f'{_checked(selected, option)}> {html.escape(option)}</label>'
        )
    return f'<div class="checkbox-grid">{"".join(boxes)}</div>'


def _field(label: str, control: str, *, required: bool = False, hint: str = "", span: bool = False, name: str | None = None) -> str:
    star = ' <span class="req">*</span>' if required else ""
    hint_html = f'<p class="hint">{html.escape(hint)}</p>' if hint else ""
    css = "field field-span" if span else "field"
    for_attr = f' for="{html.escape(name)}"' if name else ""
    return f'<div class="{css}"><label{for_attr}>{html.escape(label)}{star}</label>{control}{hint_html}</div>'


def render_claim_form_fields(draft: dict[str, Any], policies: list[dict[str, Any]], profile: dict[str, Any], email: str) -> str:
    insurance = str(draft.get("insurance_type") or "")
    if insurance not in {"motor", "property"}:
        insurance = ""
    is_motor = insurance == "motor"
    is_property = insurance == "property"

    profile_name = str(profile.get("name") or "").strip()
    first, _, last = profile_name.partition(" ")
    holder_first = draft.get("holder_first_name") or first
    holder_last = draft.get("holder_last_name") or last
    holder_email = draft.get("holder_email") or draft.get("claimant_email") or profile.get("email") or email
    holder_phone = draft.get("holder_phone") or draft.get("claimant_phone") or profile.get("phone") or ""
    selected_policy = draft.get("policy_id")
    selected_number = str(draft.get("policy_number") or "")

    options = ['<option value="">Select a policy</option>']
    for policy in policies:
        policy_id = policy["policy_id"]
        policy_number = str(policy["policy_number"])
        coverage_type = policy.get("coverage_type")
        kind = "motor" if policy_matches_insurance_type(coverage_type, "motor") else "property"
        label = html.escape(policy_number)
        if coverage_type:
            label = f"{label} — {html.escape(str(coverage_type))}"
        selected = "selected" if selected_policy is not None and int(selected_policy) == int(policy_id) else ""
        if selected:
            selected_number = policy_number
        hidden_opt = "hidden" if insurance and kind != insurance else ""
        options.append(
            f'<option value="{policy_id}" data-number="{html.escape(policy_number, quote=True)}" '
            f'data-kind="{kind}" {selected} {hidden_opt}>{label}</option>'
        )

    type_cards = []
    for value, label in INSURANCE_TYPES:
        help_text = "Allianz motor claim form, including vehicle, driver and other-party details." if value == "motor" else "Allianz property claim form, including building damage and contents."
        type_cards.append(
            f"""
            <label class="type-card">
              <span class="type-card-title">
                <input type="radio" name="insurance_type" value="{value}" required {_checked(insurance, value)}>
                <strong>{html.escape(label)}</strong>
              </span>
              <span class="type-card-help">{html.escape(help_text)}</span>
            </label>
            """
        )

    declaration_name = draft.get("declaration_name") or " ".join(part for part in (holder_first, holder_last) if part)
    relationships = MOTOR_RELATIONSHIPS if is_motor else PROPERTY_RELATIONSHIPS if is_property else MOTOR_RELATIONSHIPS + PROPERTY_RELATIONSHIPS

    return f"""
      <h2>1. What type of insurance claim is this?</h2>
      <p class="section-help">Choose motor vehicle or property first. The rest of the form follows the matching Allianz claim form.</p>
      <div class="type-pick">{''.join(type_cards)}</div>

      <div id="claim-body" {_hidden(bool(insurance))}>
      <h2>2. Policy details</h2>
      <p class="section-help">Only policies that match the insurance type you selected are listed.</p>
      <div class="form-grid">
        {_field("Policy", f'<select id="policy_id" name="policy_id" required>{"".join(options)}</select>', required=True, name="policy_id")}
        {_field("Policy number", f'<input id="policy_number" value="{_esc(selected_number)}" readonly>', hint="Automatically populated when a policy is selected.", name="policy_number")}
      </div>

      <h2>3. Policy holder details</h2>
      <div class="form-grid">
        {_field("Title", _select("holder_title", TITLES, draft.get("holder_title")), required=True, name="holder_title")}
        {_field("First name", _input("holder_first_name", holder_first, required=True), required=True, name="holder_first_name")}
        {_field("Last name", _input("holder_last_name", holder_last, required=True), required=True, name="holder_last_name")}
        {_field("Company name", _input("holder_company", draft.get("holder_company")), span=True, name="holder_company")}
        {_field("Unit number", _input("holder_unit", draft.get("holder_unit")), name="holder_unit")}
        {_field("Street number", _input("holder_street_number", draft.get("holder_street_number"), required=True), required=True, name="holder_street_number")}
        {_field("Street name", _input("holder_street_name", draft.get("holder_street_name"), required=True), required=True, name="holder_street_name")}
        {_field("Suburb", _input("holder_suburb", draft.get("holder_suburb"), required=True), required=True, name="holder_suburb")}
        {_field("State", _select("holder_state", STATES, draft.get("holder_state"), required=True), required=True, name="holder_state")}
        {_field("Postcode", _input("holder_postcode", draft.get("holder_postcode"), required=True), required=True, name="holder_postcode")}
        {_field("Preferred method of contact", _select("preferred_contact_method", CONTACT_METHODS, draft.get("preferred_contact_method"), required=True), required=True, name="preferred_contact_method")}
        {_field("Email address", _input("holder_email", holder_email, required=True, kind="email"), required=True, name="holder_email")}
        {_field("Phone number", _input("holder_phone", holder_phone, required=True, placeholder="include area code"), required=True, name="holder_phone")}
        {_field("Alternate phone number", _input("alternate_phone", draft.get("alternate_phone")), name="alternate_phone")}
      </div>
      <div id="property-postal" {_hidden(is_property)}>
        {_field("Is your postal address the same as your insured property address?", _yes_no("postal_same_as_insured", draft.get("postal_same_as_insured")), required=is_property)}
      </div>

      <h2>4. Policy holder GST details</h2>
      {_field("Are you registered for GST?", _yes_no("gst_registered", draft.get("gst_registered"), required=True), required=True)}
      <div id="gst-fields" class="form-grid" {_hidden(draft.get("gst_registered") is True)}>
        {_field("Australian Business Number (ABN)", _input("abn", draft.get("abn")), required=True, name="abn")}
        {_field("Input tax credit on the GST for this policy", _input("gst_itc_percent", draft.get("gst_itc_percent"), placeholder="%"), required=True, name="gst_itc_percent")}
      </div>

      <h2>5. EFT details</h2>
      <p class="section-help">Optional. Used if a settlement is paid to you.</p>
      <div class="form-grid">
        {_field("Account name", _input("eft_account_name", draft.get("eft_account_name")), span=True, name="eft_account_name")}
        {_field("BSB", _input("eft_bsb", draft.get("eft_bsb")), name="eft_bsb")}
        {_field("Account number", _input("eft_account_number", draft.get("eft_account_number")), name="eft_account_number")}
      </div>

      <h2>6. Incident details</h2>
      <div class="form-grid">
        {_field("Date the incident occurred", _input("incident_date", draft.get("incident_date"), required=True, kind="date"), required=True, name="incident_date")}
        {_field("Approximate time", _input("incident_time", draft.get("incident_time"), required=True, kind="time"), required=True, name="incident_time")}
      </div>
      <div id="property-claim-type" {_hidden(is_property)}>
        {_field("What type of claim are you making?", _select("property_claim_type", PROPERTY_CLAIM_TYPES, draft.get("property_claim_type") or draft.get("claim_type"), required=is_property), required=is_property, name="property_claim_type")}
      </div>
      {_field("Please tell us what happened, providing as much detail as possible", _textarea("incident_description", draft.get("incident_description"), required=True, placeholder="Describe what happened..."), required=True, span=True, name="incident_description")}
      <div id="property-at-address" {_hidden(is_property)}>
        {_field("Did the incident occur at the insured property address?", _yes_no("incident_at_insured_address", draft.get("incident_at_insured_address")), required=is_property)}
      </div>
      <div id="incident-location" {_hidden(is_motor or (is_property and draft.get("incident_at_insured_address") is False))}>
        <h3>Where did the incident occur?</h3>
        <div class="form-grid">
          {_field("Street name", _input("incident_street", draft.get("incident_street") or draft.get("incident_location")), required=is_motor, name="incident_street")}
          <div id="motor-cross-street" {_hidden(is_motor)}>{_field("Nearest cross street", _input("incident_cross_street", draft.get("incident_cross_street")), name="incident_cross_street")}</div>
          {_field("Suburb", _input("incident_suburb", draft.get("incident_suburb")), required=is_motor, name="incident_suburb")}
          {_field("State", _select("incident_state", STATES, draft.get("incident_state")), required=is_motor, name="incident_state")}
          {_field("Postcode", _input("incident_postcode", draft.get("incident_postcode")), required=is_motor, name="incident_postcode")}
        </div>
      </div>

      <h2>7. Your details</h2>
      {_field("Are you our policy holder?", _yes_no("is_policyholder", draft.get("is_policyholder"), required=True), required=True)}
      <div id="reporter-fields" {_hidden(draft.get("is_policyholder") is False)}>
        <div class="form-grid">
          {_field("What is your relationship to our policy holder?", _select("relationship_to_holder", relationships, draft.get("relationship_to_holder")), required=True, name="relationship_to_holder")}
        </div>
        <div id="reporter-reason" {_hidden(str(draft.get("relationship_to_holder") or "") == "Other")}>
          {_field("If you have selected Other, why are you and not our policy holder reporting the claim?", _textarea("reporter_reason", draft.get("reporter_reason")), span=True, name="reporter_reason")}
        </div>
        <div id="broker-fields" class="form-grid" {_hidden(is_property)}>
          {_field("Brokerage name", _input("broker_name", draft.get("broker_name")), name="broker_name")}
          {_field("Brokerage phone number", _input("broker_phone", draft.get("broker_phone")), name="broker_phone")}
          <div class="field field-span">{_field("If you are the broker or authorised representative, would you like us to send automatic claim notifications to the policy holder?", _yes_no("notify_policyholder", draft.get("notify_policyholder")))}</div>
        </div>
      </div>

      <h2>8. Witnesses</h2>
      {_field("Were there any witnesses to the incident?", _yes_no("witnesses_present", draft.get("witnesses_present"), required=True), required=True)}
      <div id="witness-fields" {_hidden(draft.get("witnesses_present") is True)}>
        {_person_block("Witness 1", "witness_1", draft, required=True)}
        {_person_block("Witness 2", "witness_2", draft)}
      </div>

      <div id="motor-injury" {_hidden(is_motor)}>
        {_field("Was any person injured in the accident?", _yes_no("person_injured", draft.get("person_injured")), required=is_motor)}
      </div>

      <h2>9. Police</h2>
      {_field("Has a police report been made?", _yes_no("police_involved", draft.get("police_involved"), required=True), required=True)}
      <div id="police-fields" class="form-grid" {_hidden(draft.get("police_involved") is True)}>
        {_field("Police report number", _input("police_report_number", draft.get("police_report_number")), name="police_report_number")}
        {_field("Date reported to police", _input("police_reported_date", draft.get("police_reported_date"), kind="date"), name="police_reported_date")}
      </div>
      <div id="motor-charges" {_hidden(is_motor and draft.get("police_involved") is True)}>
        {_field("Were any charges laid or indications made that further action may be taken?", _yes_no("charges_laid", draft.get("charges_laid")))}
        <div id="charges-details" {_hidden(draft.get("charges_laid") is True)}>
          {_field("If yes, please provide details including who and what", _textarea("charges_details", draft.get("charges_details")), span=True, name="charges_details")}
        </div>
      </div>

      <div id="motor-sections" {_hidden(is_motor)}>
        <h2>10. Driver details</h2>
        {_field("Was our insured vehicle being driven at the time of the accident?", _yes_no("vehicle_driven", draft.get("vehicle_driven")), required=is_motor)}
        <div id="driver-fields" {_hidden(draft.get("vehicle_driven") is True)}>
          {_field("If yes, was our policy holder driving the vehicle?", _yes_no("policyholder_was_driver", draft.get("policyholder_was_driver")))}
          <div class="form-grid">
            {_field("Title", _select("driver_title", TITLES, draft.get("driver_title")), name="driver_title")}
            {_field("First name", _input("driver_first_name", draft.get("driver_first_name")), name="driver_first_name")}
            {_field("Last name", _input("driver_last_name", draft.get("driver_last_name")), name="driver_last_name")}
            {_field("Date of birth", _input("driver_dob", draft.get("driver_dob"), kind="date"), name="driver_dob")}
            {_field("Phone number", _input("driver_phone", draft.get("driver_phone")), name="driver_phone")}
            {_field("Email", _input("driver_email", draft.get("driver_email"), kind="email"), name="driver_email")}
            {_field("Australian driver's licence number", _input("driver_licence_number", draft.get("driver_licence_number")), span=True, name="driver_licence_number")}
            {_field("How many years have you held an Australian or overseas driver's licence?", _input("driver_licence_years", draft.get("driver_licence_years")), span=True, name="driver_licence_years")}
            {_field("Unit number", _input("driver_unit", draft.get("driver_unit")), name="driver_unit")}
            {_field("Street number", _input("driver_street_number", draft.get("driver_street_number")), name="driver_street_number")}
            {_field("Street name", _input("driver_street_name", draft.get("driver_street_name")), name="driver_street_name")}
            {_field("Suburb", _input("driver_suburb", draft.get("driver_suburb")), name="driver_suburb")}
            {_field("State", _select("driver_state", STATES, draft.get("driver_state")), name="driver_state")}
            {_field("Postcode", _input("driver_postcode", draft.get("driver_postcode")), name="driver_postcode")}
          </div>
          {_field("As a result of the accident did the driver return a positive result to any alcohol or drugs in their system?", _yes_no("alcohol_or_drugs", draft.get("alcohol_or_drugs")))}
          <div id="alcohol-details" {_hidden(draft.get("alcohol_or_drugs") is True)}>
            {_field("If yes, please provide details", _textarea("alcohol_details", draft.get("alcohol_details")), name="alcohol_details")}
          </div>
        </div>

        <h2>11. Vehicle details</h2>
        <div class="form-grid">
          {_field("Vehicle registration number", _input("vehicle_registration", draft.get("vehicle_registration")), required=is_motor, name="vehicle_registration")}
          {_field("Vehicle type", _select("vehicle_type", VEHICLE_TYPES, draft.get("vehicle_type")), required=is_motor, name="vehicle_type")}
          {_field("Year", _input("vehicle_year", draft.get("vehicle_year")), required=is_motor, name="vehicle_year")}
          {_field("Make", _input("vehicle_make", draft.get("vehicle_make")), required=is_motor, name="vehicle_make")}
          {_field("Model", _input("vehicle_model", draft.get("vehicle_model")), name="vehicle_model")}
        </div>
        <div class="field field-span">
          <label>Vehicle damage — click the boxes that apply</label>
          {_checks("vehicle_damage", VEHICLE_DAMAGE_AREAS, draft.get("vehicle_damage") or draft.get("vehicle_damage_areas"))}
        </div>
        {_field("Was the vehicle towed?", _yes_no("vehicle_towed", draft.get("vehicle_towed")), required=is_motor)}
        <div id="towed-fields" {_hidden(draft.get("vehicle_towed") is True)}>
          {_field("If yes, where is the vehicle now?", _input("vehicle_now_location", draft.get("vehicle_now_location")), name="vehicle_now_location")}
        </div>
        {_field("As a result of the impact were any of the airbags deployed?", _yes_no("airbags_deployed", draft.get("airbags_deployed")), required=is_motor)}
        {_field("At the time of impact was the vehicle travelling more than 40 kilometres per hour?", _yes_no("speed_over_40", draft.get("speed_over_40")), required=is_motor)}

        <h2>12. Other persons</h2>
        {_field("Was another person's vehicle involved in this incident?", _yes_no("other_vehicle_involved", draft.get("other_vehicle_involved")), required=is_motor)}
        {_field("Was another person's property (not a vehicle) damaged in this incident?", _yes_no("other_property_damaged", draft.get("other_property_damaged")), required=is_motor)}
        <div id="motor-other-fields" {_hidden(draft.get("other_vehicle_involved") is True or draft.get("other_property_damaged") is True)}>
          {_other_party_block(1, draft, include_vehicle=True)}
          {_other_party_block(2, draft, include_vehicle=True)}
        </div>

        <h2>13. Disclosure</h2>
        <p class="section-help">In the past 3 years has the policy holder or the driver in this incident:</p>
        {_field("Had a driver's licence cancelled, disqualified or suspended?", _yes_no("licence_cancelled_3yrs", draft.get("licence_cancelled_3yrs")), required=is_motor)}
        <div id="fine-defaults" {_hidden(draft.get("licence_cancelled_3yrs") is True)}>
          {_field("If yes, was the driver's licence cancelled, disqualified or suspended as a result of fine defaults?", _yes_no("cancelled_fine_defaults", draft.get("cancelled_fine_defaults")))}
        </div>
        {_field("Been convicted or had any fines or penalties imposed for any alcohol related driving offences or crime involving drugs, dishonesty, arson, theft, fraud or violence against any person or property?", _yes_no("convicted_alcohol_crime_3yrs", draft.get("convicted_alcohol_crime_3yrs")), required=is_motor)}
        <p class="section-help">In the past 5 years has the driver in this incident:</p>
        {_field("Had an insurance policy declined or cancelled or had any conditions imposed on an insurance policy?", _yes_no("insurance_declined_5yrs", draft.get("insurance_declined_5yrs")), required=is_motor)}
      </div>

      <div id="property-sections" {_hidden(is_property)}>
        <h2>10. Building damage</h2>
        {_field("Does the claim include damage to your building?", _yes_no("building_damaged", draft.get("building_damaged")), required=is_property)}
        <div id="building-fields" {_hidden(draft.get("building_damaged") is True)}>
          <div class="field field-span">
            <label>Select the damage area(s)</label>
            {_checks("building_area", BUILDING_AREAS, draft.get("building_area") or draft.get("building_areas"))}
          </div>
          <div class="form-grid">
            {_field("Bathroom — number of room(s)", _input("bathroom_rooms", draft.get("bathroom_rooms")), name="bathroom_rooms")}
            {_field("Bedroom — number of room(s)", _input("bedroom_rooms", draft.get("bedroom_rooms")), name="bedroom_rooms")}
            {_field("Lounge / family room — number of room(s)", _input("lounge_rooms", draft.get("lounge_rooms")), name="lounge_rooms")}
          </div>
          <p class="section-help">Select the area(s) that have been damaged and provide specific details.</p>
          {_field("Carpet", _textarea("damage_carpet", draft.get("damage_carpet")), name="damage_carpet")}
          {_field("Ceiling", _textarea("damage_ceiling", draft.get("damage_ceiling")), name="damage_ceiling")}
          {_field("Floor", _textarea("damage_floor", draft.get("damage_floor")), name="damage_floor")}
          {_field("Wall", _textarea("damage_wall", draft.get("damage_wall")), name="damage_wall")}
          {_field("Windows", _textarea("damage_windows", draft.get("damage_windows")), name="damage_windows")}
          {_field("Other", _textarea("damage_other", draft.get("damage_other")), name="damage_other")}
          {_field("Is the property now secure?", _yes_no("property_secure", draft.get("property_secure")))}
          {_field("Have you had any damage to the building repaired?", _yes_no("repairs_done", draft.get("repairs_done")))}
          {_field("Is the property habitable?", _yes_no("property_habitable", draft.get("property_habitable")))}
        </div>

        <h2>11. Contents</h2>
        {_field("Does the claim include damage, loss or theft of your contents?", _yes_no("contents_affected", draft.get("contents_affected")), required=is_property)}
        <div id="contents-fields" {_hidden(draft.get("contents_affected") is True)}>
          <p class="section-help">Select the contents item(s) and provide a description of each item, including the age, size, when and where purchased.</p>
          {_contents_table(draft)}
          {_field("Total estimated replacement value", _input("contents_total_value", draft.get("contents_total_value"), placeholder="$0.00"), name="contents_total_value")}
        </div>

        <h2>12. Other persons</h2>
        {_field("Was another person responsible for the damage, loss or theft?", _yes_no("other_person_responsible", draft.get("other_person_responsible")), required=is_property)}
        <div id="property-other-fields" {_hidden(draft.get("other_person_responsible") is True)}>
          {_other_party_block(1, draft, include_vehicle=False)}
          {_other_party_block(2, draft, include_vehicle=False)}
        </div>

        <h2>13. Disclosure</h2>
        <p class="section-help">In the past 5 years, has the policy holder:</p>
        {_field("Been convicted of, or had any fines or penalties imposed, for any crime?", _yes_no("convicted_crime_5yrs", draft.get("convicted_crime_5yrs")), required=is_property)}
        {_field("Had an insurance policy declined or cancelled or had any conditions imposed on an insurance policy?", _yes_no("insurance_declined_5yrs", draft.get("insurance_declined_5yrs")), required=True)}
      </div>

      <h2>14. Supporting documents</h2>
      <div class="field file-drop">
        <label for="files">Supporting evidence</label>
        <input id="files" name="files" type="file" multiple accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf">
        <p class="hint">Photos, receipts, repair quotes, invoices or police reports. JPEG, PNG or PDF. Maximum 25 MB per file.</p>
      </div>
      {_field("Additional comments", _textarea("additional_comments", draft.get("additional_comments"), placeholder="Anything else you'd like us to know..."), name="additional_comments")}

      <h2>15. Declaration</h2>
      <p class="section-help">I certify that I am authorised to submit this claim, that I am authorised to provide this information, and that to the best of my knowledge the information given in this form is truthful, accurate and complete. I understand that this claim may be refused if the information is untrue, inaccurate or incomplete.</p>
      <div class="field">
        <label class="check-row">
          <input id="declaration_accepted" name="declaration_accepted" type="checkbox" value="yes" required {"checked" if draft.get("declaration_accepted") else ""}>
          <span>I confirm the declaration above. <span class="req">*</span></span>
        </label>
      </div>
      <div class="form-grid">
        {_field("Signature / name of insured", _input("declaration_name", declaration_name), name="declaration_name")}
        {_field("Position held", _input("declaration_position", draft.get("declaration_position")), hint="Only fill this in if you are signing on behalf of someone else, for example as a broker, director or authorised representative. Leave blank if you are the policy holder signing for yourself.", name="declaration_position")}
        {_field("Date", _input("declaration_date", draft.get("declaration_date") or date.today(), kind="date"), name="declaration_date")}
      </div>
      </div>
    """ + _form_script()


def _person_block(heading: str, prefix: str, draft: dict[str, Any], *, required: bool = False) -> str:
    return f"""
      <h3>{html.escape(heading)}</h3>
      <div class="form-grid">
        {_field("Title", _select(f"{prefix}_title", TITLES, draft.get(f"{prefix}_title"), required=required), required=required, name=f"{prefix}_title")}
        {_field("First name", _input(f"{prefix}_first_name", draft.get(f"{prefix}_first_name"), required=required), required=required, name=f"{prefix}_first_name")}
        {_field("Last name", _input(f"{prefix}_last_name", draft.get(f"{prefix}_last_name"), required=required), required=required, name=f"{prefix}_last_name")}
        {_field("Unit number", _input(f"{prefix}_unit", draft.get(f"{prefix}_unit")), name=f"{prefix}_unit")}
        {_field("Street number", _input(f"{prefix}_street_number", draft.get(f"{prefix}_street_number")), name=f"{prefix}_street_number")}
        {_field("Street name", _input(f"{prefix}_street_name", draft.get(f"{prefix}_street_name")), name=f"{prefix}_street_name")}
        {_field("Suburb", _input(f"{prefix}_suburb", draft.get(f"{prefix}_suburb")), name=f"{prefix}_suburb")}
        {_field("State", _select(f"{prefix}_state", STATES, draft.get(f"{prefix}_state")), name=f"{prefix}_state")}
        {_field("Postcode", _input(f"{prefix}_postcode", draft.get(f"{prefix}_postcode")), name=f"{prefix}_postcode")}
        {_field("Phone number", _input(f"{prefix}_phone", draft.get(f"{prefix}_phone"), required=required), required=required, name=f"{prefix}_phone")}
        {_field("Email", _input(f"{prefix}_email", draft.get(f"{prefix}_email"), kind="email"), name=f"{prefix}_email")}
      </div>
    """


def _other_party_block(index: int, draft: dict[str, Any], *, include_vehicle: bool) -> str:
    prefix = f"other_{index}"
    vehicle = ""
    if include_vehicle:
        vehicle = f"""
        <h4>Other person's vehicle details</h4>
        <div class="form-grid">
          {_field("Vehicle registration number", _input(f"{prefix}_vehicle_registration", draft.get(f"{prefix}_vehicle_registration")), name=f"{prefix}_vehicle_registration")}
          {_field("Vehicle type", _select(f"{prefix}_vehicle_type", VEHICLE_TYPES, draft.get(f"{prefix}_vehicle_type")), name=f"{prefix}_vehicle_type")}
          {_field("Year", _input(f"{prefix}_vehicle_year", draft.get(f"{prefix}_vehicle_year")), name=f"{prefix}_vehicle_year")}
          {_field("Make", _input(f"{prefix}_vehicle_make", draft.get(f"{prefix}_vehicle_make")), name=f"{prefix}_vehicle_make")}
          {_field("Model", _input(f"{prefix}_vehicle_model", draft.get(f"{prefix}_vehicle_model")), name=f"{prefix}_vehicle_model")}
        </div>
        <div class="field field-span">
          <label>Where their car was damaged</label>
          {_checks(f"{prefix}_vehicle_damage", VEHICLE_DAMAGE_AREAS, draft.get(f"{prefix}_vehicle_damage") or draft.get(f"{prefix}_vehicle_damage_areas"))}
        </div>
        """
    else:
        vehicle = f"""
        <div class="form-grid">
          {_field("Other person's vehicle registration", _input(f"{prefix}_vehicle_registration", draft.get(f"{prefix}_vehicle_registration")), name=f"{prefix}_vehicle_registration")}
        </div>
        """
    return f"""
      <h3>Other person {index}</h3>
      <div class="form-grid">
        {_field("Title", _select(f"{prefix}_title", TITLES, draft.get(f"{prefix}_title")), name=f"{prefix}_title")}
        {_field("First name", _input(f"{prefix}_first_name", draft.get(f"{prefix}_first_name")), name=f"{prefix}_first_name")}
        {_field("Last name", _input(f"{prefix}_last_name", draft.get(f"{prefix}_last_name")), name=f"{prefix}_last_name")}
        {_field("Company name", _input(f"{prefix}_company_name", draft.get(f"{prefix}_company_name")), span=True, name=f"{prefix}_company_name")}
        {_field("Unit number", _input(f"{prefix}_unit", draft.get(f"{prefix}_unit")), name=f"{prefix}_unit")}
        {_field("Street number", _input(f"{prefix}_street_number", draft.get(f"{prefix}_street_number")), name=f"{prefix}_street_number")}
        {_field("Street name", _input(f"{prefix}_street_name", draft.get(f"{prefix}_street_name")), name=f"{prefix}_street_name")}
        {_field("Suburb", _input(f"{prefix}_suburb", draft.get(f"{prefix}_suburb")), name=f"{prefix}_suburb")}
        {_field("State", _select(f"{prefix}_state", STATES, draft.get(f"{prefix}_state")), name=f"{prefix}_state")}
        {_field("Postcode", _input(f"{prefix}_postcode", draft.get(f"{prefix}_postcode")), name=f"{prefix}_postcode")}
        {_field("Phone number", _input(f"{prefix}_phone", draft.get(f"{prefix}_phone")), name=f"{prefix}_phone")}
        {_field("Email", _input(f"{prefix}_email", draft.get(f"{prefix}_email"), kind="email"), name=f"{prefix}_email")}
        {_field("Other person's insurance company", _input(f"{prefix}_insurance_company", draft.get(f"{prefix}_insurance_company")), name=f"{prefix}_insurance_company")}
        {_field("Other person's insurance policy number", _input(f"{prefix}_insurance_policy_number", draft.get(f"{prefix}_insurance_policy_number")), name=f"{prefix}_insurance_policy_number")}
        {_field("Other person's insurance claim number", _input(f"{prefix}_insurance_claim_number", draft.get(f"{prefix}_insurance_claim_number")), name=f"{prefix}_insurance_claim_number")}
        {_field("Other person's licence number", _input(f"{prefix}_licence_number", draft.get(f"{prefix}_licence_number")), name=f"{prefix}_licence_number")}
      </div>
      {vehicle}
    """


def _contents_table(draft: dict[str, Any]) -> str:
    rows = []
    for category, label in CONTENTS_CATEGORIES:
        rows.append(
            f"""<tr>
              <td>{html.escape(label)}</td>
              <td><input name="contents_{category}_description" value="{_esc(draft.get(f"contents_{category}_description"))}" placeholder="Description, age, where purchased"></td>
              <td><input name="contents_{category}_value" value="{_esc(draft.get(f"contents_{category}_value"))}" placeholder="$0.00"></td>
            </tr>"""
        )
    return f"""
      <table class="data">
        <thead><tr><th>Item</th><th>Description</th><th>Estimated replacement value</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def _form_script() -> str:
    return r"""
    <script>
      const typeInputs = document.querySelectorAll("input[name='insurance_type']");
      const claimBody = document.getElementById("claim-body");
      const policy = document.getElementById("policy_id");
      const policyNumber = document.getElementById("policy_number");
      const motorSections = document.getElementById("motor-sections");
      const propertySections = document.getElementById("property-sections");

      function setSectionDisabled(root, disabled) {
        if (!root) return;
        root.querySelectorAll("input, select, textarea").forEach((el) => { el.disabled = disabled; });
      }
      function selectedType() {
        const checked = document.querySelector("input[name='insurance_type']:checked");
        return checked ? checked.value : "";
      }
      function syncType() {
        const type = selectedType();
        claimBody.hidden = !type;
        motorSections.hidden = type !== "motor";
        propertySections.hidden = type !== "property";
        document.getElementById("property-postal").hidden = type !== "property";
        document.getElementById("property-claim-type").hidden = type !== "property";
        document.getElementById("property-at-address").hidden = type !== "property";
        document.getElementById("motor-injury").hidden = type !== "motor";
        document.getElementById("motor-cross-street").hidden = type !== "motor";
        document.getElementById("broker-fields").hidden = type !== "property" || document.getElementById("reporter-fields").hidden;
        setSectionDisabled(claimBody, !type);
        if (type) {
          setSectionDisabled(motorSections, type !== "motor");
          setSectionDisabled(propertySections, type !== "property");
          setSectionDisabled(document.getElementById("motor-injury"), type !== "motor");
          setSectionDisabled(document.getElementById("motor-charges"), type !== "motor");
          setSectionDisabled(document.getElementById("property-postal"), type !== "property");
          setSectionDisabled(document.getElementById("property-claim-type"), type !== "property");
          setSectionDisabled(document.getElementById("property-at-address"), type !== "property");
          setSectionDisabled(document.getElementById("broker-fields"), type !== "property");
        }
        syncPolicyFilter(type);
        syncIncidentLocation();
        syncMotorCharges();
        document.querySelectorAll(".type-card").forEach((card) => {
          card.classList.toggle("selected", card.querySelector("input").checked);
        });
      }
      function syncPolicyFilter(type) {
        Array.from(policy.options).forEach((opt, index) => {
          if (index === 0) return;
          const match = !type || opt.dataset.kind === type;
          opt.hidden = !match;
          if (!match && opt.selected) {
            policy.selectedIndex = 0;
            policyNumber.value = "";
          }
        });
      }
      function syncPolicy() {
        const opt = policy.options[policy.selectedIndex];
        policyNumber.value = opt && opt.dataset.number ? opt.dataset.number : "";
      }
      function yes(name) {
        const input = document.querySelector("input[name='" + name + "']:checked");
        return input ? input.value === "yes" : null;
      }
      function bindToggle(name, targetId, showYes) {
        const target = document.getElementById(targetId);
        if (!target) return;
        document.querySelectorAll("input[name='" + name + "']").forEach((input) => {
          input.addEventListener("change", () => {
            const on = showYes === false ? input.value === "no" : input.value === "yes";
            target.hidden = !on || !input.checked;
            if (name === "is_policyholder") {
              document.getElementById("broker-fields").hidden = selectedType() !== "property" || target.hidden;
            }
            if (name === "incident_at_insured_address" || name === "police_involved") {
              syncIncidentLocation();
              syncMotorCharges();
            }
          });
        });
      }
      function syncIncidentLocation() {
        const type = selectedType();
        const atHome = yes("incident_at_insured_address");
        const show = type === "motor" || (type === "property" && atHome === false);
        document.getElementById("incident-location").hidden = !show;
      }
      function syncMotorCharges() {
        document.getElementById("motor-charges").hidden = selectedType() !== "motor" || yes("police_involved") !== true;
      }
      typeInputs.forEach((input) => input.addEventListener("change", syncType));
      policy.addEventListener("change", syncPolicy);
      bindToggle("gst_registered", "gst-fields");
      bindToggle("is_policyholder", "reporter-fields", false);
      bindToggle("witnesses_present", "witness-fields");
      bindToggle("police_involved", "police-fields");
      bindToggle("charges_laid", "charges-details");
      bindToggle("vehicle_driven", "driver-fields");
      bindToggle("alcohol_or_drugs", "alcohol-details");
      bindToggle("vehicle_towed", "towed-fields");
      bindToggle("licence_cancelled_3yrs", "fine-defaults");
      bindToggle("building_damaged", "building-fields");
      bindToggle("contents_affected", "contents-fields");
      bindToggle("other_person_responsible", "property-other-fields");
      function syncMotorOthers() {
        const show = yes("other_vehicle_involved") === true || yes("other_property_damaged") === true;
        document.getElementById("motor-other-fields").hidden = !show;
      }
      ["other_vehicle_involved", "other_property_damaged", "incident_at_insured_address"].forEach((name) => {
        document.querySelectorAll("input[name='" + name + "']").forEach((input) => {
          input.addEventListener("change", () => {
            syncMotorOthers();
            syncIncidentLocation();
          });
        });
      });
      document.querySelectorAll("select[name='relationship_to_holder']").forEach((select) => {
        select.addEventListener("change", () => {
          document.getElementById("reporter-reason").hidden = select.value !== "Other";
        });
      });
      const nameFirst = document.getElementById("holder_first_name");
      const nameLast = document.getElementById("holder_last_name");
      const decName = document.getElementById("declaration_name");
      function syncDeclName() {
        if (!decName.dataset.touched) decName.value = [nameFirst.value, nameLast.value].filter(Boolean).join(" ");
      }
      nameFirst.addEventListener("input", syncDeclName);
      nameLast.addEventListener("input", syncDeclName);
      decName.addEventListener("input", () => { decName.dataset.touched = "1"; });
      syncType();
      syncMotorOthers();
    </script>
    """
