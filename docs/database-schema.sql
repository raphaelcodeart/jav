--
-- PostgreSQL database dump
--

\restrict 0a0qXTYucsXCmZ9Yn5socFFxbrTK6v6hdcvq5ttcWofznu52iivvrfMqPhlHjp6

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: game; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA game;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: belt_exams; Type: TABLE; Schema: game; Owner: -
--

CREATE TABLE game.belt_exams (
    id uuid NOT NULL,
    player_id uuid NOT NULL,
    belt character varying(16) NOT NULL,
    score_pct smallint NOT NULL,
    passed_at timestamp with time zone NOT NULL
);


--
-- Name: careers; Type: TABLE; Schema: game; Owner: -
--

CREATE TABLE game.careers (
    player_id uuid NOT NULL,
    state jsonb NOT NULL,
    week integer NOT NULL,
    belt character varying(16) NOT NULL,
    saves integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: players; Type: TABLE; Schema: game; Owner: -
--

CREATE TABLE game.players (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    display_name character varying(80) NOT NULL,
    club_label character varying(120),
    quiz_xp bigint NOT NULL,
    career_xp bigint NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: quiz_attempts; Type: TABLE; Schema: game; Owner: -
--

CREATE TABLE game.quiz_attempts (
    id uuid NOT NULL,
    player_id uuid NOT NULL,
    quiz_id character varying(40) NOT NULL,
    lang character varying(2) NOT NULL,
    questions jsonb NOT NULL,
    answers jsonb NOT NULL,
    score integer NOT NULL,
    max_score integer NOT NULL,
    correct smallint NOT NULL,
    passed boolean NOT NULL,
    xp_earned integer NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone
);


--
-- Name: addresses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.addresses (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    street character varying(255) NOT NULL,
    city character varying(128) NOT NULL,
    province character varying(8) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country character varying(2) NOT NULL,
    id uuid NOT NULL
);


--
-- Name: agent_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_profiles (
    organization_id uuid NOT NULL,
    user_id uuid,
    display_name character varying(255) NOT NULL,
    first_name character varying(120),
    last_name character varying(120),
    promoter_code character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    photo_url character varying(1000),
    joined_at timestamp with time zone NOT NULL,
    current_rank_id uuid,
    approved_by_user_id uuid,
    approved_at timestamp with time zone,
    rejection_reason character varying(500),
    is_blacklisted boolean NOT NULL,
    collaboration_contract_version character varying(32),
    collaboration_accepted_documents jsonb NOT NULL,
    collaboration_accepted_at timestamp with time zone,
    collaboration_otp_verified_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: agent_rank_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_rank_history (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    rank_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    calculation_source character varying(32) NOT NULL,
    rule_version_id character varying(32) NOT NULL,
    approved_by uuid,
    reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: attribution_corrections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attribution_corrections (
    organization_id uuid NOT NULL,
    customer_attribution_id uuid NOT NULL,
    previous_promoter_code_id uuid NOT NULL,
    new_promoter_code_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    reason character varying(500) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    organization_id uuid NOT NULL,
    actor_user_id uuid,
    action character varying(128) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    previous_value jsonb,
    new_value jsonb,
    reason character varying(500),
    ip_address character varying(64),
    user_agent character varying(255),
    correlation_id character varying(64),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: cart_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cart_items (
    cart_id uuid NOT NULL,
    quantity bigint NOT NULL,
    jav_market_variant_id uuid,
    product_version_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_cart_items_exactly_one_reference CHECK ((num_nonnulls(jav_market_variant_id, product_version_id) = 1)),
    CONSTRAINT ck_cart_items_quantity_max CHECK ((quantity <= 99)),
    CONSTRAINT ck_cart_items_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: carts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.carts (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    shop character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_carts_shop CHECK (((shop)::text = ANY ((ARRAY['jav_market'::character varying, 'catalog'::character varying])::text[])))
);


--
-- Name: club_applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_applications (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    full_name character varying(200) NOT NULL,
    birth_date date,
    email character varying(200),
    data jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(12) DEFAULT 'PENDING'::character varying NOT NULL,
    internal_notes text,
    athlete_id uuid,
    referred_by character varying(200),
    first_time boolean,
    joined_year smallint,
    decided_at timestamp with time zone,
    decided_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_applications_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: club_athlete_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athlete_documents (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    kind character varying(24) NOT NULL,
    description character varying(250),
    storage_key character varying(500) NOT NULL,
    original_filename character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes integer NOT NULL,
    uploaded_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_athlete_documents_kind CHECK (((kind)::text = ANY ((ARRAY['SOCIAL_SECURITY'::character varying, 'MEDICAL_JUSTIFICATION'::character varying, 'SCHOOL_JUSTIFICATION'::character varying, 'CLUB_DECLARATION'::character varying, 'PARENTAL_AUTHORIZATION'::character varying, 'ID_DOCUMENT'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- Name: club_athlete_login_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athlete_login_codes (
    organization_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    created_by_user_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    last_used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: club_athlete_media; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athlete_media (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    kind character varying(8) NOT NULL,
    url character varying(500),
    youtube_id character varying(11),
    caption character varying(200),
    published boolean DEFAULT false NOT NULL,
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_athlete_media_kind CHECK (((kind)::text = ANY ((ARRAY['PHOTO'::character varying, 'VIDEO'::character varying])::text[]))),
    CONSTRAINT ck_club_athlete_media_kind_payload CHECK (((((kind)::text = 'PHOTO'::text) AND (url IS NOT NULL) AND (youtube_id IS NULL)) OR (((kind)::text = 'VIDEO'::text) AND (youtube_id IS NOT NULL) AND (url IS NULL))))
);


--
-- Name: club_athlete_public_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athlete_public_profiles (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    consent_given_at timestamp with time zone,
    consent_by_user_id uuid,
    show_photo boolean DEFAULT false NOT NULL,
    bio character varying(280),
    published boolean DEFAULT false NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    ijf_profile_url character varying(300),
    favorite_technique character varying(80),
    dominant_side character varying(5),
    CONSTRAINT ck_club_athlete_public_profiles_dominant_side CHECK (((dominant_side IS NULL) OR ((dominant_side)::text = ANY ((ARRAY['LEFT'::character varying, 'RIGHT'::character varying])::text[]))))
);


--
-- Name: club_athlete_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athlete_records (
    athlete_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    address character varying(250),
    postal_code character varying(20),
    city character varying(100),
    phone character varying(30),
    mobile character varying(30),
    email character varying(150),
    marital_status character varying(30),
    id_document_type character varying(20),
    id_document_number character varying(50),
    id_document_check_digits character varying(20),
    id_document_expires_on date,
    passport_number character varying(50),
    passport_country character varying(60),
    passport_expires_on date,
    guardian_name character varying(200),
    guardian_phone character varying(30),
    father_phone character varying(30),
    mother_phone character varying(30),
    guardian_fiscal_code character varying(20),
    guardian_id_document_type character varying(20),
    guardian_id_document_number character varying(50),
    guardian_id_document_check_digits character varying(20),
    guardian_id_document_expires_on date,
    guardian_passport_number character varying(50),
    guardian_passport_country character varying(60),
    guardian_passport_expires_on date,
    notes text,
    updated_at timestamp with time zone NOT NULL,
    updated_by_user_id uuid,
    CONSTRAINT ck_club_athlete_records_guardian_id_document_type CHECK (((guardian_id_document_type IS NULL) OR ((guardian_id_document_type)::text = ANY ((ARRAY['CITIZEN_CARD'::character varying, 'PASSPORT'::character varying, 'RESIDENCE_PERMIT'::character varying, 'BIRTH_CERTIFICATE'::character varying, 'OTHER'::character varying])::text[])))),
    CONSTRAINT ck_club_athlete_records_id_document_type CHECK (((id_document_type IS NULL) OR ((id_document_type)::text = ANY ((ARRAY['CITIZEN_CARD'::character varying, 'PASSPORT'::character varying, 'RESIDENCE_PERMIT'::character varying, 'BIRTH_CERTIFICATE'::character varying, 'OTHER'::character varying])::text[]))))
);


--
-- Name: club_athlete_supports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athlete_supports (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    category character varying(16) NOT NULL,
    amount_cents bigint NOT NULL,
    note character varying(300),
    paid_on date NOT NULL,
    recorded_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_athlete_supports_amount_positive CHECK ((amount_cents > 0)),
    CONSTRAINT ck_club_athlete_supports_category CHECK (((category)::text = ANY ((ARRAY['TRANSPORT'::character varying, 'MATERIAL'::character varying, 'COMPETITION'::character varying, 'EXAM'::character varying, 'TRAINING_CAMP'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- Name: club_athletes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_athletes (
    organization_id uuid NOT NULL,
    guardian_user_id uuid NOT NULL,
    first_name character varying(80) NOT NULL,
    last_name character varying(80) NOT NULL,
    birth_date date NOT NULL,
    sex character varying(1) NOT NULL,
    fiscal_code character varying(16),
    photo_url character varying(500),
    is_self boolean NOT NULL,
    plan_id uuid,
    plan_locked boolean NOT NULL,
    status character varying(16) NOT NULL,
    weight_kg numeric(5,1),
    federation_number character varying(32),
    federation_expires_on date,
    joined_on date NOT NULL,
    left_on date,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    social_tier character varying(1),
    adapted_judo boolean DEFAULT false NOT NULL,
    user_id uuid,
    member_number character varying(20),
    kimono_name character varying(100),
    height_cm smallint,
    nationality character varying(80),
    weight_category character varying(30),
    federation_renewal_year smallint,
    exempt_monthly boolean DEFAULT false NOT NULL,
    exempt_annual boolean DEFAULT false NOT NULL,
    custom_discount_kind character varying(8),
    custom_discount_value integer,
    custom_discount_scope character varying(8) DEFAULT 'MONTHLY'::character varying NOT NULL,
    custom_discount_note character varying(200),
    white_judogi boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_club_athletes_custom_discount_kind CHECK (((custom_discount_kind IS NULL) OR ((custom_discount_kind)::text = ANY ((ARRAY['PERCENT'::character varying, 'FIXED'::character varying])::text[])))),
    CONSTRAINT ck_club_athletes_custom_discount_scope CHECK (((custom_discount_scope)::text = ANY ((ARRAY['MONTHLY'::character varying, 'ANNUAL'::character varying, 'BOTH'::character varying])::text[]))),
    CONSTRAINT ck_club_athletes_custom_discount_value CHECK (((custom_discount_kind IS NULL) OR ((custom_discount_value > 0) AND (((custom_discount_kind)::text <> 'PERCENT'::text) OR (custom_discount_value <= 100))))),
    CONSTRAINT ck_club_athletes_height_range CHECK (((height_cm IS NULL) OR ((height_cm > 40) AND (height_cm < 250)))),
    CONSTRAINT ck_club_athletes_sex CHECK (((sex)::text = ANY ((ARRAY['M'::character varying, 'F'::character varying])::text[]))),
    CONSTRAINT ck_club_athletes_social_tier CHECK (((social_tier IS NULL) OR ((social_tier)::text = ANY ((ARRAY['A'::character varying, 'B'::character varying, 'C'::character varying, 'D'::character varying])::text[])))),
    CONSTRAINT ck_club_athletes_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'SUSPENDED'::character varying, 'LEFT'::character varying])::text[]))),
    CONSTRAINT ck_club_athletes_weight_positive CHECK (((weight_kg IS NULL) OR (weight_kg > (0)::numeric)))
);


--
-- Name: club_attendances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_attendances (
    organization_id uuid NOT NULL,
    course_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    date date NOT NULL,
    present boolean NOT NULL,
    recorded_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    note character varying(300),
    recorded_by_kind character varying(8) DEFAULT 'STAFF'::character varying NOT NULL
);


--
-- Name: club_belt_grades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_belt_grades (
    organization_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    grade character varying(16) NOT NULL,
    awarded_on date NOT NULL,
    awarded_by_user_id uuid,
    note character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    CONSTRAINT ck_club_belt_grades_grade CHECK (((grade)::text = ANY ((ARRAY['WHITE'::character varying, 'WHITE_BARS_3'::character varying, 'WHITE_BARS_6'::character varying, 'WHITE_BARS_9'::character varying, 'WHITE_BARS_12'::character varying, 'WHITE_YELLOW'::character varying, 'YELLOW'::character varying, 'YELLOW_ORANGE'::character varying, 'ORANGE'::character varying, 'ORANGE_GREEN'::character varying, 'GREEN'::character varying, 'GREEN_BLUE'::character varying, 'BLUE'::character varying, 'BLUE_BROWN'::character varying, 'BROWN'::character varying, 'BLACK_1'::character varying, 'BLACK_2'::character varying, 'BLACK_3'::character varying, 'BLACK_4'::character varying, 'BLACK_5'::character varying, 'BLACK_6'::character varying, 'BLACK_7'::character varying, 'BLACK_8'::character varying, 'BLACK_9'::character varying, 'BLACK_10'::character varying])::text[])))
);


--
-- Name: club_change_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_change_requests (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    requested_by_user_id uuid,
    field character varying(20) NOT NULL,
    current_value character varying(200),
    requested_value character varying(200) NOT NULL,
    note character varying(500),
    status character varying(12) DEFAULT 'PENDING'::character varying NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by_user_id uuid,
    resolution_note character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_change_requests_field CHECK (((field)::text = ANY ((ARRAY['BELT'::character varying, 'WEIGHT_CATEGORY'::character varying, 'WEIGHT'::character varying])::text[]))),
    CONSTRAINT ck_club_change_requests_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying])::text[])))
);


--
-- Name: club_cleaning_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_cleaning_logs (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    performed_at timestamp with time zone NOT NULL,
    person_name character varying(150) NOT NULL,
    hours numeric(5,2) NOT NULL,
    hourly_rate_cents bigint NOT NULL,
    total_cents bigint NOT NULL,
    notes text,
    signature_storage_key character varying(500),
    paid_on date,
    expense_id uuid,
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_cleaning_logs_hours_positive CHECK ((hours > (0)::numeric)),
    CONSTRAINT ck_club_cleaning_logs_rate_positive CHECK ((hourly_rate_cents > 0)),
    CONSTRAINT ck_club_cleaning_logs_total_non_negative CHECK ((total_cents >= 0))
);


--
-- Name: club_competition_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_competition_entries (
    organization_id uuid NOT NULL,
    competition_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    category character varying(120),
    weight_kg numeric(5,1),
    status character varying(16) NOT NULL,
    registered_by_user_id uuid NOT NULL,
    placement smallint,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    rank smallint,
    result_notes character varying(500),
    CONSTRAINT ck_club_competition_entries_placement CHECK (((placement IS NULL) OR (placement = ANY (ARRAY[0, 1, 2, 3, 5, 7])))),
    CONSTRAINT ck_club_competition_entries_status CHECK (((status)::text = ANY ((ARRAY['REGISTERED'::character varying, 'WITHDRAWN'::character varying])::text[])))
);


--
-- Name: club_competitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_competitions (
    organization_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    starts_on date NOT NULL,
    ends_on date NOT NULL,
    location character varying(200),
    organizer character varying(200),
    level character varying(24) NOT NULL,
    registration_deadline date NOT NULL,
    fee_cents bigint NOT NULL,
    requires_agonistic_certificate boolean NOT NULL,
    min_age integer,
    max_age integer,
    categories text,
    status character varying(16) NOT NULL,
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid,
    kind character varying(16) DEFAULT 'COMPETITION'::character varying NOT NULL,
    transport_needed boolean DEFAULT false NOT NULL,
    transport_entity_name character varying(200),
    transport_entity_email character varying(255),
    transport_departure character varying(300),
    transport_return character varying(300),
    transport_companions integer DEFAULT 0 NOT NULL,
    transport_notes text,
    transport_auto_send boolean DEFAULT false NOT NULL,
    transport_mode character varying(8) DEFAULT 'TBC'::character varying NOT NULL,
    transport_info character varying(300),
    starts_at_time time without time zone,
    ends_at_time time without time zone,
    registration_deadline_time time without time zone,
    places integer,
    age_groups character varying(20)[] DEFAULT '{}'::character varying[] NOT NULL,
    circular_url character varying(500),
    circular_filename character varying(255),
    image_url character varying(500),
    CONSTRAINT ck_club_competitions_age_range CHECK (((max_age IS NULL) OR (min_age IS NULL) OR (max_age >= min_age))),
    CONSTRAINT ck_club_competitions_date_range CHECK ((ends_on >= starts_on)),
    CONSTRAINT ck_club_competitions_deadline_before_start CHECK ((registration_deadline <= starts_on)),
    CONSTRAINT ck_club_competitions_fee_non_negative CHECK ((fee_cents >= 0)),
    CONSTRAINT ck_club_competitions_kind CHECK (((kind)::text = ANY ((ARRAY['COMPETITION'::character varying, 'STAGE'::character varying, 'REFEREEING'::character varying, 'EDUCATION'::character varying, 'MEETING'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT ck_club_competitions_level CHECK (((level)::text = ANY ((ARRAY['CLUB'::character varying, 'REGIONAL'::character varying, 'ZONAL'::character varying, 'OPENS'::character varying, 'NATIONAL'::character varying, 'INTERNATIONAL'::character varying, 'EUROPEAN_CUP'::character varying, 'EUROPEAN_CHAMPIONSHIP'::character varying, 'WORLD_CHAMPIONSHIP'::character varying, 'OLYMPIC_GAMES'::character varying])::text[]))),
    CONSTRAINT ck_club_competitions_places_positive CHECK (((places IS NULL) OR (places > 0))),
    CONSTRAINT ck_club_competitions_status CHECK (((status)::text = ANY ((ARRAY['OPEN'::character varying, 'CLOSED'::character varying, 'DONE'::character varying])::text[]))),
    CONSTRAINT ck_club_competitions_transport_companions_non_negative CHECK ((transport_companions >= 0)),
    CONSTRAINT ck_club_competitions_transport_mode CHECK (((transport_mode)::text = ANY ((ARRAY['CLUB'::character varying, 'OWN'::character varying, 'TBC'::character varying])::text[])))
);


--
-- Name: club_consents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_consents (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    user_id uuid,
    athlete_id uuid,
    kind character varying(20) NOT NULL,
    granted boolean NOT NULL,
    policy_version character varying(20) NOT NULL,
    source character varying(12) NOT NULL,
    recorded_by_user_id uuid,
    ip_hash character varying(64),
    given_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_consents_kind CHECK (((kind)::text = ANY ((ARRAY['PRIVACY_POLICY'::character varying, 'PHOTOS'::character varying, 'MARKETING'::character varying])::text[]))),
    CONSTRAINT ck_club_consents_source CHECK (((source)::text = ANY ((ARRAY['PORTAL'::character varying, 'BACKOFFICE'::character varying, 'LEGACY'::character varying])::text[]))),
    CONSTRAINT ck_club_consents_subject CHECK (((((kind)::text = 'PRIVACY_POLICY'::text) AND (user_id IS NOT NULL)) OR (((kind)::text <> 'PRIVACY_POLICY'::text) AND (athlete_id IS NOT NULL))))
);


--
-- Name: club_course_athletes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_course_athletes (
    course_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: club_course_slots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_course_slots (
    course_id uuid NOT NULL,
    weekday smallint NOT NULL,
    starts_at time without time zone NOT NULL,
    ends_at time without time zone NOT NULL,
    room character varying(60),
    id uuid NOT NULL,
    CONSTRAINT ck_club_course_slots_time_range CHECK ((ends_at > starts_at)),
    CONSTRAINT ck_club_course_slots_weekday_range CHECK (((weekday >= 0) AND (weekday <= 6)))
);


--
-- Name: club_course_staff; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_course_staff (
    course_id uuid NOT NULL,
    user_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: club_courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_courses (
    organization_id uuid NOT NULL,
    name character varying(120) NOT NULL,
    description character varying(500),
    level character varying(60),
    min_age integer,
    max_age integer,
    instructor_user_id uuid,
    active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    venue_name character varying(200),
    venue_address character varying(300),
    venue_city character varying(120),
    public_description text,
    public_coach_name character varying(80),
    coach_share_pct numeric(5,2),
    published boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_club_courses_age_range CHECK (((max_age IS NULL) OR (min_age IS NULL) OR (max_age >= min_age))),
    CONSTRAINT ck_club_courses_coach_share_pct_range CHECK (((coach_share_pct IS NULL) OR ((coach_share_pct >= (0)::numeric) AND (coach_share_pct <= (100)::numeric))))
);


--
-- Name: club_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_documents (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    category character varying(20) NOT NULL,
    title character varying(200) NOT NULL,
    issued_on date,
    expires_on date,
    notes text,
    storage_key character varying(500) NOT NULL,
    original_filename character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes integer NOT NULL,
    uploaded_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    shared_with_members boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_club_documents_category CHECK (((category)::text = ANY ((ARRAY['DECLARATION'::character varying, 'FEDERATION'::character varying, 'MINUTES'::character varying, 'TAX'::character varying, 'SOCIAL_SECURITY'::character varying, 'SPORTS'::character varying, 'INSURANCE'::character varying, 'STATUTES'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT ck_club_documents_date_range CHECK (((expires_on IS NULL) OR (issued_on IS NULL) OR (expires_on >= issued_on)))
);


--
-- Name: club_equipment_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_equipment_orders (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    requested_by_user_id uuid,
    kimono_name character varying(100) NOT NULL,
    kimono_type character varying(24) NOT NULL,
    color character varying(40) NOT NULL,
    brand character varying(60) NOT NULL,
    size_cm smallint NOT NULL,
    price_cents bigint,
    trade_in jsonb,
    notes text,
    internal_notes text,
    status character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    fee_id uuid,
    delivered_on date,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_equipment_orders_kimono_type CHECK (((kimono_type)::text = ANY ((ARRAY['FIJ_APPROVED'::character varying, 'TRAINING'::character varying, 'SEMI_COMPETITION'::character varying, 'COMPETITION_NOT_APPROVED'::character varying])::text[]))),
    CONSTRAINT ck_club_equipment_orders_price_non_negative CHECK (((price_cents IS NULL) OR (price_cents >= 0))),
    CONSTRAINT ck_club_equipment_orders_size_range CHECK (((size_cm >= 80) AND (size_cm <= 220))),
    CONSTRAINT ck_club_equipment_orders_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'IN_PREPARATION'::character varying, 'DELIVERED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: club_expenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_expenses (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    spent_on date NOT NULL,
    category character varying(16) NOT NULL,
    amount_cents bigint NOT NULL,
    description character varying(200) NOT NULL,
    supplier character varying(200),
    payment_method character varying(16) NOT NULL,
    receipt_storage_key character varying(500),
    receipt_filename character varying(255),
    receipt_content_type character varying(100),
    created_by_user_id uuid,
    recurring_id uuid,
    period character varying(7),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_expenses_amount_positive CHECK ((amount_cents > 0)),
    CONSTRAINT ck_club_expenses_category CHECK (((category)::text = ANY ((ARRAY['RENT'::character varying, 'STAFF'::character varying, 'FEDERATION'::character varying, 'INSURANCE'::character varying, 'EQUIPMENT'::character varying, 'TRANSPORT'::character varying, 'EVENTS'::character varying, 'UTILITIES'::character varying, 'MARKETING'::character varying, 'ADMIN'::character varying, 'COLLABORATORS'::character varying, 'CLEANING'::character varying, 'EXTERNAL_COACH'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT ck_club_expenses_payment_method CHECK (((payment_method)::text = ANY ((ARRAY['BANK_TRANSFER'::character varying, 'MBWAY'::character varying, 'CASH'::character varying, 'CARD'::character varying, 'DIRECT_DEBIT'::character varying, 'CHEQUE'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT ck_club_expenses_recurring_period CHECK (((recurring_id IS NULL) = (period IS NULL)))
);


--
-- Name: club_external_coach_fees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_external_coach_fees (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    coach_name character varying(150) NOT NULL,
    month date NOT NULL,
    weekday_hours numeric(6,2) NOT NULL,
    weekday_rate_cents bigint NOT NULL,
    weekend_hours numeric(6,2) NOT NULL,
    weekend_rate_cents bigint NOT NULL,
    students integer NOT NULL,
    per_student_cents bigint NOT NULL,
    total_cents bigint NOT NULL,
    status character varying(10) DEFAULT 'PENDING'::character varying NOT NULL,
    paid_cents bigint,
    paid_on date,
    payment_method character varying(16),
    reference character varying(100),
    notes text,
    expense_id uuid,
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_external_coach_fees_paid_non_negative CHECK (((paid_cents IS NULL) OR (paid_cents >= 0))),
    CONSTRAINT ck_club_external_coach_fees_quantities_non_negative CHECK (((weekday_hours >= (0)::numeric) AND (weekend_hours >= (0)::numeric) AND (students >= 0))),
    CONSTRAINT ck_club_external_coach_fees_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'PAID'::character varying, 'PARTIAL'::character varying, 'EXEMPT'::character varying])::text[]))),
    CONSTRAINT ck_club_external_coach_fees_total_non_negative CHECK ((total_cents >= 0))
);


--
-- Name: club_fees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_fees (
    organization_id uuid NOT NULL,
    athlete_id uuid,
    kind character varying(16) NOT NULL,
    period character varying(40) NOT NULL,
    description character varying(200) NOT NULL,
    amount_cents bigint NOT NULL,
    due_date date NOT NULL,
    status character varying(16) NOT NULL,
    competition_id uuid,
    paid_at timestamp with time zone,
    paid_via_proof_id uuid,
    paid_by_user_id uuid,
    payment_note character varying(500),
    waived_by_user_id uuid,
    waived_at timestamp with time zone,
    waive_reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    guardian_user_id uuid,
    gross_amount_cents bigint,
    discount_cents bigint DEFAULT 0 NOT NULL,
    discount_note character varying(200),
    absence_adjustment character varying(8),
    course_id uuid,
    coach_user_id uuid,
    coach_share_pct numeric(5,2),
    payment_method character varying(16),
    cash_received_by_user_id uuid,
    cash_received_by_name character varying(120),
    installment_no smallint,
    installments_total smallint,
    CONSTRAINT ck_club_fees_absence_adjustment CHECK (((absence_adjustment IS NULL) OR ((absence_adjustment)::text = ANY ((ARRAY['HALF'::character varying, 'FULL'::character varying])::text[])))),
    CONSTRAINT ck_club_fees_amount_non_negative CHECK ((amount_cents >= 0)),
    CONSTRAINT ck_club_fees_coach_share_pct_range CHECK (((coach_share_pct IS NULL) OR ((coach_share_pct >= (0)::numeric) AND (coach_share_pct <= (100)::numeric)))),
    CONSTRAINT ck_club_fees_discount_non_negative CHECK ((discount_cents >= 0)),
    CONSTRAINT ck_club_fees_installments CHECK ((((installment_no IS NULL) AND (installments_total IS NULL)) OR ((installment_no >= 1) AND (installments_total >= 2) AND (installment_no <= installments_total)))),
    CONSTRAINT ck_club_fees_kind CHECK (((kind)::text = ANY ((ARRAY['MONTHLY'::character varying, 'ENROLLMENT'::character varying, 'COMPETITION'::character varying, 'MEMBERSHIP'::character varying, 'FINE'::character varying, 'EQUIPMENT'::character varying])::text[]))),
    CONSTRAINT ck_club_fees_owner CHECK (((((kind)::text = 'MEMBERSHIP'::text) AND (athlete_id IS NULL) AND (guardian_user_id IS NOT NULL)) OR (((kind)::text <> 'MEMBERSHIP'::text) AND (athlete_id IS NOT NULL)))),
    CONSTRAINT ck_club_fees_payment_method CHECK (((payment_method IS NULL) OR ((payment_method)::text = ANY ((ARRAY['BANK_TRANSFER'::character varying, 'MBWAY'::character varying, 'CASH'::character varying, 'CARD'::character varying, 'WALLET'::character varying])::text[])))),
    CONSTRAINT ck_club_fees_status CHECK (((status)::text = ANY ((ARRAY['DUE'::character varying, 'PAID'::character varying, 'WAIVED'::character varying])::text[])))
);


--
-- Name: club_functions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_functions (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    function character varying(24) NOT NULL,
    user_id uuid,
    athlete_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_functions_function CHECK (((function)::text = ANY ((ARRAY['COACH'::character varying, 'ASSISTANT_COACH'::character varying, 'MONITOR'::character varying, 'ASSISTANT_MONITOR'::character varying])::text[]))),
    CONSTRAINT ck_club_functions_one_person CHECK (((user_id IS NULL) <> (athlete_id IS NULL)))
);


--
-- Name: club_medical_certificates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_medical_certificates (
    organization_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    type character varying(16) NOT NULL,
    issued_on date NOT NULL,
    expires_on date NOT NULL,
    storage_key character varying(500) NOT NULL,
    original_filename character varying(255) NOT NULL,
    uploaded_by_user_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    CONSTRAINT ck_club_medical_certificates_date_range CHECK ((expires_on >= issued_on)),
    CONSTRAINT ck_club_medical_certificates_type CHECK (((type)::text = ANY ((ARRAY['NON_AGONISTIC'::character varying, 'AGONISTIC'::character varying])::text[])))
);


--
-- Name: club_news_likes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_news_likes (
    post_id uuid NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: club_news_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_news_posts (
    organization_id uuid NOT NULL,
    club_id uuid,
    title character varying(200) NOT NULL,
    body text,
    image_url character varying(500),
    video_url character varying(500),
    link_url character varying(500),
    pinned boolean DEFAULT false NOT NULL,
    published boolean DEFAULT true NOT NULL,
    published_at timestamp with time zone NOT NULL,
    author_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    audience character varying(8) DEFAULT 'CLUB'::character varying NOT NULL,
    CONSTRAINT ck_club_news_posts_audience CHECK (((audience)::text = ANY ((ARRAY['CLUB'::character varying, 'NETWORK'::character varying])::text[]))),
    CONSTRAINT ck_club_news_posts_platform_is_network CHECK (((club_id IS NOT NULL) OR ((audience)::text = 'NETWORK'::text)))
);


--
-- Name: club_payment_proof_fees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_payment_proof_fees (
    proof_id uuid NOT NULL,
    fee_id uuid NOT NULL,
    id uuid NOT NULL
);


--
-- Name: club_payment_proofs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_payment_proofs (
    organization_id uuid NOT NULL,
    uploaded_by_user_id uuid NOT NULL,
    storage_key character varying(500),
    original_filename character varying(255),
    content_type character varying(100),
    amount_cents bigint NOT NULL,
    note character varying(500),
    status character varying(16) NOT NULL,
    reviewed_by_user_id uuid,
    reviewed_at timestamp with time zone,
    rejection_reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    credit_cents bigint DEFAULT 0 NOT NULL,
    method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    cash_received_by_user_id uuid,
    cash_received_by_name character varying(120),
    receipt_number character varying(24),
    paid_on date,
    CONSTRAINT ck_club_payment_proofs_amount_non_negative CHECK ((amount_cents >= 0)),
    CONSTRAINT ck_club_payment_proofs_cash_receiver CHECK ((((method)::text <> 'CASH'::text) OR (cash_received_by_user_id IS NOT NULL) OR (cash_received_by_name IS NOT NULL))),
    CONSTRAINT ck_club_payment_proofs_credit_range CHECK (((credit_cents >= 0) AND (credit_cents <= amount_cents))),
    CONSTRAINT ck_club_payment_proofs_file_or_credit CHECK (((storage_key IS NOT NULL) OR (credit_cents = amount_cents) OR ((method)::text = 'CASH'::text))),
    CONSTRAINT ck_club_payment_proofs_method CHECK (((method)::text = ANY ((ARRAY['BANK_TRANSFER'::character varying, 'MBWAY'::character varying, 'CASH'::character varying])::text[]))),
    CONSTRAINT ck_club_payment_proofs_status CHECK (((status)::text = ANY ((ARRAY['ACCEPTED'::character varying, 'REJECTED'::character varying])::text[])))
);


--
-- Name: club_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_plans (
    organization_id uuid NOT NULL,
    name character varying(120) NOT NULL,
    description character varying(500),
    min_age integer NOT NULL,
    max_age integer,
    monthly_fee_cents bigint NOT NULL,
    enrollment_fee_cents bigint NOT NULL,
    due_day smallint NOT NULL,
    billing_months smallint[] NOT NULL,
    active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid NOT NULL,
    CONSTRAINT ck_club_plans_age_range CHECK (((max_age IS NULL) OR (max_age >= min_age))),
    CONSTRAINT ck_club_plans_due_day_range CHECK (((due_day >= 1) AND (due_day <= 28))),
    CONSTRAINT ck_club_plans_enrollment_fee_non_negative CHECK ((enrollment_fee_cents >= 0)),
    CONSTRAINT ck_club_plans_min_age_non_negative CHECK ((min_age >= 0)),
    CONSTRAINT ck_club_plans_monthly_fee_non_negative CHECK ((monthly_fee_cents >= 0))
);


--
-- Name: club_platform_fees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_platform_fees (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    pct numeric(5,2) NOT NULL,
    valid_from date NOT NULL,
    set_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_platform_fees_first_of_month CHECK ((EXTRACT(day FROM valid_from) = (1)::numeric)),
    CONSTRAINT ck_club_platform_fees_pct_range CHECK (((pct >= (0)::numeric) AND (pct <= (100)::numeric)))
);


--
-- Name: club_receipt_counters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_receipt_counters (
    club_id uuid NOT NULL,
    prefix character varying(4) NOT NULL,
    year smallint NOT NULL,
    last_number integer NOT NULL
);


--
-- Name: club_recurring_expenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_recurring_expenses (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    category character varying(16) NOT NULL,
    amount_cents bigint NOT NULL,
    description character varying(200) NOT NULL,
    supplier character varying(200),
    payment_method character varying(16) NOT NULL,
    day_of_month smallint NOT NULL,
    starts_on date NOT NULL,
    ends_on date,
    active boolean DEFAULT true NOT NULL,
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_recurring_expenses_amount_positive CHECK ((amount_cents > 0)),
    CONSTRAINT ck_club_recurring_expenses_category CHECK (((category)::text = ANY ((ARRAY['RENT'::character varying, 'STAFF'::character varying, 'FEDERATION'::character varying, 'INSURANCE'::character varying, 'EQUIPMENT'::character varying, 'TRANSPORT'::character varying, 'EVENTS'::character varying, 'UTILITIES'::character varying, 'MARKETING'::character varying, 'ADMIN'::character varying, 'COLLABORATORS'::character varying, 'CLEANING'::character varying, 'EXTERNAL_COACH'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT ck_club_recurring_expenses_date_range CHECK (((ends_on IS NULL) OR (ends_on >= starts_on))),
    CONSTRAINT ck_club_recurring_expenses_day_of_month_range CHECK (((day_of_month >= 1) AND (day_of_month <= 28))),
    CONSTRAINT ck_club_recurring_expenses_payment_method CHECK (((payment_method)::text = ANY ((ARRAY['BANK_TRANSFER'::character varying, 'MBWAY'::character varying, 'CASH'::character varying, 'CARD'::character varying, 'DIRECT_DEBIT'::character varying, 'CHEQUE'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- Name: club_referees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_referees (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    user_id uuid,
    athlete_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_referees_one_person CHECK (((user_id IS NULL) <> (athlete_id IS NULL)))
);


--
-- Name: club_reminders_sent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_reminders_sent (
    organization_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    entity_id character varying(80) NOT NULL,
    stage character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: club_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_reports (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    kind character varying(16) NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    storage_key character varying(500) NOT NULL,
    download_name character varying(200) NOT NULL,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_reports_kind CHECK (((kind)::text = 'ACTIVITIES'::text))
);


--
-- Name: club_school_letters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_school_letters (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    entry_id uuid NOT NULL,
    competition_id uuid NOT NULL,
    athlete_id uuid NOT NULL,
    body_text text NOT NULL,
    storage_key character varying(500) NOT NULL,
    generated_at timestamp with time zone NOT NULL,
    generated_by_user_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: club_sites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_sites (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    tagline character varying(200),
    about text,
    city character varying(120),
    hero_image_url character varying(500),
    logo_url character varying(500),
    gallery jsonb DEFAULT '[]'::jsonb NOT NULL,
    coaches jsonb DEFAULT '[]'::jsonb NOT NULL,
    contact_phone character varying(40),
    contact_email character varying(255),
    address character varying(300),
    map_url character varying(500),
    instagram_url character varying(500),
    facebook_url character varying(500),
    youtube_url character varying(500),
    website_url character varying(500),
    published boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    show_prices boolean DEFAULT false NOT NULL,
    brand_primary character varying(7),
    brand_secondary character varying(7),
    brand_accent character varying(7),
    founded_year smallint,
    venue character varying(160),
    highlights jsonb DEFAULT '[]'::jsonb NOT NULL,
    history jsonb DEFAULT '[]'::jsonb NOT NULL,
    pillars jsonb DEFAULT '[]'::jsonb NOT NULL,
    news jsonb DEFAULT '[]'::jsonb NOT NULL,
    videos jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT ck_club_sites_brand_accent CHECK (((brand_accent IS NULL) OR ((brand_accent)::text ~ '^#[0-9A-F]{6}$'::text))),
    CONSTRAINT ck_club_sites_brand_primary CHECK (((brand_primary IS NULL) OR ((brand_primary)::text ~ '^#[0-9A-F]{6}$'::text))),
    CONSTRAINT ck_club_sites_brand_secondary CHECK (((brand_secondary IS NULL) OR ((brand_secondary)::text ~ '^#[0-9A-F]{6}$'::text))),
    CONSTRAINT ck_club_sites_founded_year CHECK (((founded_year IS NULL) OR ((founded_year >= 1882) AND (founded_year <= 2100))))
);


--
-- Name: club_staff_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_staff_messages (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    staff_user_id uuid NOT NULL,
    channel character varying(8) NOT NULL,
    from_staff boolean NOT NULL,
    author_user_id uuid NOT NULL,
    body text NOT NULL,
    read_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_staff_messages_channel CHECK (((channel)::text = ANY ((ARRAY['CLUB'::character varying, 'JAV'::character varying])::text[])))
);


--
-- Name: club_staff_rates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_staff_rates (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    user_id uuid NOT NULL,
    hourly_rate_cents bigint NOT NULL,
    valid_from date NOT NULL,
    set_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_staff_rates_rate_non_negative CHECK ((hourly_rate_cents >= 0))
);


--
-- Name: club_staff_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_staff_tasks (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    user_id uuid,
    person_name character varying(150) NOT NULL,
    kind character varying(10) NOT NULL,
    title character varying(200) NOT NULL,
    done_on date NOT NULL,
    minutes integer,
    cost_cents bigint DEFAULT 0 NOT NULL,
    note character varying(500),
    paid_on date,
    expense_id uuid,
    recorded_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_staff_tasks_cost_not_negative CHECK ((cost_cents >= 0)),
    CONSTRAINT ck_club_staff_tasks_kind CHECK (((kind)::text = ANY ((ARRAY['TASK'::character varying, 'ODD_JOB'::character varying])::text[]))),
    CONSTRAINT ck_club_staff_tasks_minutes_positive CHECK (((minutes IS NULL) OR (minutes > 0)))
);


--
-- Name: club_transport_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_transport_requests (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    competition_id uuid NOT NULL,
    to_email character varying(255),
    subject character varying(300) NOT NULL,
    body_text text NOT NULL,
    status character varying(16) NOT NULL,
    athletes_count integer NOT NULL,
    sent_at timestamp with time zone,
    sent_by_user_id uuid,
    last_error character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_transport_requests_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'SENT'::character varying])::text[])))
);


--
-- Name: club_work_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.club_work_sessions (
    organization_id uuid NOT NULL,
    club_id uuid NOT NULL,
    user_id uuid NOT NULL,
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    note character varying(300),
    corrected_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_club_work_sessions_time_range CHECK (((ended_at IS NULL) OR (ended_at > started_at)))
);


--
-- Name: clubs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clubs (
    organization_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(80) NOT NULL,
    status character varying(16) NOT NULL,
    settings jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    kind character varying(16) DEFAULT 'CLUB'::character varying NOT NULL,
    CONSTRAINT ck_clubs_kind CHECK (((kind)::text = ANY ((ARRAY['CLUB'::character varying, 'JAV_COURSES'::character varying])::text[]))),
    CONSTRAINT ck_clubs_slug_format CHECK (((slug)::text ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text)),
    CONSTRAINT ck_clubs_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'SUSPENDED'::character varying])::text[])))
);


--
-- Name: commission_adjustments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_adjustments (
    organization_id uuid NOT NULL,
    original_movement_id uuid NOT NULL,
    new_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_calculation_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_calculation_steps (
    calculation_id uuid NOT NULL,
    step_order integer NOT NULL,
    beneficiary_agent_id uuid NOT NULL,
    rank_at_calculation character varying(16),
    base_amount_cents bigint NOT NULL,
    already_distributed_cents bigint NOT NULL,
    entrepreneurial_difference_cents bigint NOT NULL,
    personal_bonus_cents bigint NOT NULL,
    gross_amount_cents bigint NOT NULL,
    movement_type character varying(32) NOT NULL,
    explanation character varying(1000) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_calculations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_calculations (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    network_snapshot_id uuid NOT NULL,
    commission_plan_version_id uuid,
    trigger_event_id uuid NOT NULL,
    input_snapshot jsonb NOT NULL,
    output_snapshot jsonb NOT NULL,
    checksum character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_movements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_movements (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    origin_event_id uuid NOT NULL,
    calculation_id uuid NOT NULL,
    movement_type character varying(32) NOT NULL,
    amount_cents bigint NOT NULL,
    currency character varying(3) NOT NULL,
    status character varying(32) NOT NULL,
    effective_date date NOT NULL,
    scheduled_date date,
    paid_date date,
    rule_version_id character varying(32) NOT NULL,
    network_snapshot_id uuid NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_offsets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_offsets (
    organization_id uuid NOT NULL,
    debit_movement_id uuid NOT NULL,
    credit_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_plan_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_plan_versions (
    organization_id uuid NOT NULL,
    version_label character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_reversals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_reversals (
    organization_id uuid NOT NULL,
    original_movement_id uuid NOT NULL,
    new_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_rule_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_rule_versions (
    commission_plan_version_id uuid NOT NULL,
    rule_type character varying(64) NOT NULL,
    parameters jsonb NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    customer_id uuid NOT NULL,
    company_name character varying(255) NOT NULL,
    legal_form character varying(64),
    sdi_code character varying(16)
);


--
-- Name: contact_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contact_messages (
    organization_id uuid NOT NULL,
    club_id uuid,
    name character varying(120) NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(40),
    message text NOT NULL,
    locale character varying(5) DEFAULT 'pt'::character varying NOT NULL,
    status character varying(10) DEFAULT 'NEW'::character varying NOT NULL,
    consent_at timestamp with time zone NOT NULL,
    ip_hash character varying(64),
    user_agent character varying(200),
    emailed_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    topic character varying(16) DEFAULT 'GENERAL'::character varying NOT NULL,
    CONSTRAINT ck_contact_messages_status CHECK (((status)::text = ANY ((ARRAY['NEW'::character varying, 'READ'::character varying, 'ARCHIVED'::character varying])::text[]))),
    CONSTRAINT ck_contact_messages_topic CHECK (((topic)::text = ANY ((ARRAY['GENERAL'::character varying, 'SPONSOR'::character varying, 'ENROLMENT'::character varying, 'EVENTS'::character varying, 'NEW_CLUB'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- Name: contract_attributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_attributions (
    organization_id uuid NOT NULL,
    producer_agent_id uuid NOT NULL,
    attributed_promoter_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_commission_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_commission_plans (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    accepted_by_user_id uuid NOT NULL,
    accepted_at timestamp with time zone NOT NULL,
    payment_plan character varying(16),
    total_commission_cents bigint NOT NULL,
    preview jsonb NOT NULL,
    checksum character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_events (
    contract_id uuid NOT NULL,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_instalments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_instalments (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    number integer NOT NULL,
    instalments_total integer NOT NULL,
    due_date date NOT NULL,
    amount_cents bigint NOT NULL,
    status character varying(16) NOT NULL,
    paid_at timestamp with time zone,
    payment_source character varying(16),
    confirmed_by_user_id uuid,
    commission_event_id uuid,
    commission_released_at timestamp with time zone,
    commission_calculation_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_requests (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    holder_first_name character varying(128),
    holder_last_name character varying(128),
    email character varying(320),
    pec character varying(320),
    iban character varying(34),
    holder_kind character varying(32),
    company_name character varying(255),
    legal_rep_fiscal_code character varying(16),
    holder_fiscal_code character varying(16),
    holder_birth_date date,
    holder_birth_place character varying(160),
    holder_birth_place_code character varying(4),
    street character varying(255),
    city character varying(128),
    province character varying(8),
    postal_code character varying(16),
    created_by_user_id uuid,
    created_by_role character varying(32),
    activated_by_promoter_id uuid,
    submitted_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    updated_at timestamp with time zone,
    notes text,
    notes_updated_by_user_id uuid,
    notes_updated_at timestamp with time zone,
    bank_transfer_requested_at timestamp with time zone,
    bank_transfer_total_cents bigint,
    bank_transfer_confirmed_at timestamp with time zone,
    bank_transfer_confirmed_by_user_id uuid,
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_status_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_status_history (
    contract_id uuid NOT NULL,
    from_status character varying(32),
    to_status character varying(32) NOT NULL,
    actor_user_id uuid NOT NULL,
    reason character varying(500),
    notes character varying(2000),
    correlation_id character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contracts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contracts (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    contract_request_id uuid NOT NULL,
    product_version_id uuid,
    contract_attribution_id uuid,
    network_snapshot_id uuid,
    status character varying(32) NOT NULL,
    notes character varying(2000),
    iban character varying(34),
    email character varying(320),
    holder_first_name character varying(128),
    holder_last_name character varying(128),
    pec character varying(320),
    activated_at timestamp with time zone,
    expires_at timestamp with time zone,
    updated_at timestamp with time zone,
    created_by_user_id uuid,
    created_by_role character varying(32),
    activated_by_promoter_id uuid,
    first_referrer_agent_id uuid,
    customer_kind character varying(32),
    net_amount_cents bigint,
    vat_rate numeric(5,2),
    vat_amount_cents bigint,
    gross_amount_cents bigint,
    instalments_net_amount_cents bigint,
    instalments_vat_amount_cents bigint,
    instalments_gross_amount_cents bigint,
    payment_plan character varying(16),
    payment_method character varying(16),
    paid_at timestamp with time zone,
    cashback_credited_at timestamp with time zone,
    terms_accepted_at timestamp with time zone,
    terms_accepted_by_user_id uuid,
    terms_version character varying(32),
    terms_accepted_ip character varying(45),
    terms_accepted_user_agent character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_contracts_product_required CHECK (((product_version_id IS NOT NULL) OR ((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'CANCELLED'::character varying])::text[]))))
);


--
-- Name: customer_attributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_attributions (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    referral_session_id uuid,
    attributed_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: customer_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_profiles (
    customer_id uuid NOT NULL,
    first_name character varying(128) NOT NULL,
    last_name character varying(128) NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    organization_id uuid NOT NULL,
    user_id uuid,
    kind character varying(32) NOT NULL,
    fiscal_code character varying(32),
    vat_number character varying(32),
    email character varying(255) NOT NULL,
    phone character varying(32),
    pec character varying(255),
    photo_url character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: documentation_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documentation_posts (
    organization_id uuid NOT NULL,
    title character varying(200) NOT NULL,
    body text,
    audience character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    image_url character varying(500),
    pdf_url character varying(500),
    pdf_filename character varying(255),
    video_url character varying(500),
    created_by_user_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    organization_id uuid NOT NULL,
    contract_id uuid,
    contract_request_id uuid,
    document_type character varying(32) NOT NULL,
    description character varying(120),
    original_filename character varying(255) NOT NULL,
    storage_key character varying(500) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes bigint NOT NULL,
    uploaded_by_user_id uuid NOT NULL,
    uploaded_by_role character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    reviewed_by_user_id uuid,
    reviewed_at timestamp with time zone,
    review_note character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_documents_one_owner CHECK ((num_nonnulls(contract_id, contract_request_id) = 1))
);


--
-- Name: domain_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_outbox (
    organization_id uuid NOT NULL,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    processed_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: email_template_overrides; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_template_overrides (
    key character varying(40) NOT NULL,
    subject character varying(200) NOT NULL,
    heading character varying(200) NOT NULL,
    body text NOT NULL,
    cta_label character varying(80),
    updated_at timestamp with time zone NOT NULL,
    updated_by_user_id uuid
);


--
-- Name: email_verification_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_verification_tokens (
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: friend_referral_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.friend_referral_codes (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: friend_referral_reward_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.friend_referral_reward_claims (
    organization_id uuid NOT NULL,
    referrer_user_id uuid NOT NULL,
    milestone integer NOT NULL,
    status character varying(16) NOT NULL,
    handled_by_user_id uuid,
    handled_at timestamp with time zone,
    note character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: friend_referrals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.friend_referrals (
    organization_id uuid NOT NULL,
    referrer_user_id uuid NOT NULL,
    referred_customer_id uuid NOT NULL,
    code_used character varying(32) NOT NULL,
    source character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: jav_market_order_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_order_items (
    order_id uuid NOT NULL,
    product_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    quantity integer NOT NULL,
    unit_price_cents bigint NOT NULL,
    unit_cost_cents bigint,
    product_name character varying(255) NOT NULL,
    variant_label character varying(255),
    producer_name character varying(160),
    credit_discount_percentage integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    producer_id uuid,
    supplier_dispatch_id uuid,
    CONSTRAINT ck_jav_market_order_items_quantity_positive CHECK ((quantity > 0))
);


--
-- Name: shop_order_number_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shop_order_number_seq
    START WITH 1000
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jav_market_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    athlete_id uuid,
    created_by_user_id uuid NOT NULL,
    number bigint DEFAULT nextval('public.shop_order_number_seq'::regclass) NOT NULL,
    items_cents bigint NOT NULL,
    shipping_cents bigint NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint NOT NULL,
    bank_transfer_discount_cents bigint NOT NULL,
    vat_percentage integer NOT NULL,
    vat_amount_cents bigint NOT NULL,
    vat_mode character varying(16) DEFAULT 'ADDED'::character varying NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) NOT NULL,
    payment_method character varying(16) NOT NULL,
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    recipient_name character varying(128) NOT NULL,
    recipient_phone character varying(32),
    address_line1 character varying(255) NOT NULL,
    address_line2 character varying(255),
    city character varying(128) NOT NULL,
    province character varying(64) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country_code character varying(2) NOT NULL,
    shipping_days character varying(32),
    fulfillment_status character varying(16) NOT NULL,
    forwarded_at timestamp with time zone,
    forwarded_by_user_id uuid,
    forward_error character varying(500),
    tracking_number character varying(128),
    tracking_url character varying(1000),
    tracking_company character varying(128),
    shipped_at timestamp with time zone,
    delivered_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid,
    CONSTRAINT ck_jav_market_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_jav_market_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents)),
    CONSTRAINT ck_jav_market_orders_vat_mode CHECK (((vat_mode)::text = ANY ((ARRAY['INCLUDED'::character varying, 'ADDED'::character varying])::text[])))
);


--
-- Name: jav_market_producers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_producers (
    organization_id uuid NOT NULL,
    name character varying(160) NOT NULL,
    description character varying(4000) NOT NULL,
    website_url character varying(1000),
    logo_url character varying(1000),
    vat_number character varying(32),
    email character varying(255),
    phone character varying(32),
    address character varying(500),
    active boolean NOT NULL,
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: jav_market_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_products (
    organization_id uuid NOT NULL,
    producer_id uuid,
    name character varying(255) NOT NULL,
    description character varying(8000) NOT NULL,
    image_url character varying(1000),
    images jsonb NOT NULL,
    status character varying(16) NOT NULL,
    credit_discount_percentage integer NOT NULL,
    unit_cost_cents bigint,
    created_by_user_id uuid NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid,
    CONSTRAINT ck_jav_market_products_credit_percentage_range CHECK (((credit_discount_percentage >= 0) AND (credit_discount_percentage <= 99)))
);


--
-- Name: jav_market_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_settings (
    organization_id uuid NOT NULL,
    enabled boolean NOT NULL,
    shipping_mode character varying(16) NOT NULL,
    shipping_flat_cents integer NOT NULL,
    shipping_days character varying(32),
    min_order_cents integer DEFAULT 0 NOT NULL,
    free_shipping_threshold_cents integer,
    ship_to_country character varying(2) NOT NULL,
    auto_forward boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    supplier_email_from character varying(255),
    supplier_email_signature character varying(1000)
);


--
-- Name: jav_market_supplier_dispatches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_supplier_dispatches (
    organization_id uuid NOT NULL,
    producer_id uuid NOT NULL,
    source character varying(16) NOT NULL,
    to_email character varying(255) NOT NULL,
    subject character varying(255) NOT NULL,
    body_text text NOT NULL,
    sent_at timestamp with time zone NOT NULL,
    sent_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_jav_market_supplier_dispatches_source CHECK (((source)::text = ANY ((ARRAY['QUEUE'::character varying, 'ORDER'::character varying, 'AUTO'::character varying, 'LEGACY'::character varying])::text[])))
);


--
-- Name: jav_market_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jav_market_variants (
    product_id uuid NOT NULL,
    label character varying(255) NOT NULL,
    sku character varying(128),
    image_url character varying(1000),
    price_cents bigint NOT NULL,
    inventory integer,
    active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_jav_market_variants_price_positive CHECK ((price_cents > 0))
);


--
-- Name: javbot_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.javbot_conversations (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    club_id uuid,
    state jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: javbot_instructions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.javbot_instructions (
    organization_id uuid NOT NULL,
    club_id uuid,
    text text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    updated_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: javbot_knowledge_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.javbot_knowledge_chunks (
    document_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    club_id uuid,
    ordinal integer NOT NULL,
    page integer NOT NULL,
    text text NOT NULL,
    norm text NOT NULL,
    id uuid NOT NULL
);


--
-- Name: javbot_knowledge_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.javbot_knowledge_documents (
    organization_id uuid NOT NULL,
    club_id uuid,
    title character varying(200) NOT NULL,
    filename character varying(255) NOT NULL,
    storage_key character varying(512) NOT NULL,
    size_bytes integer NOT NULL,
    page_count integer DEFAULT 0 NOT NULL,
    char_count integer DEFAULT 0 NOT NULL,
    status character varying(16) NOT NULL,
    uploaded_by_user_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: javbot_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.javbot_messages (
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    club_id uuid,
    role character varying(8) NOT NULL,
    text text NOT NULL,
    actions jsonb DEFAULT '[]'::jsonb NOT NULL,
    quick_replies jsonb DEFAULT '[]'::jsonb NOT NULL,
    intent character varying(40),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: javbot_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.javbot_tasks (
    organization_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    club_id uuid,
    kind character varying(32) NOT NULL,
    payload jsonb NOT NULL,
    status character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    result_ref character varying(64),
    done_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: legacy_import_map; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.legacy_import_map (
    source character varying(32) NOT NULL,
    source_table character varying(64) NOT NULL,
    source_id character varying(100) NOT NULL,
    target_table character varying(64) NOT NULL,
    target_id uuid NOT NULL,
    imported_at timestamp with time zone NOT NULL,
    id uuid NOT NULL
);


--
-- Name: network_assignment_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_assignment_history (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    old_parent_agent_id uuid,
    new_parent_agent_id uuid,
    requested_by uuid NOT NULL,
    approved_by uuid,
    reason character varying(500) NOT NULL,
    effective_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: network_closure; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_closure (
    organization_id uuid NOT NULL,
    ancestor_agent_id uuid NOT NULL,
    descendant_agent_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    depth integer NOT NULL,
    effective_to timestamp with time zone
);


--
-- Name: network_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_edges (
    organization_id uuid NOT NULL,
    parent_agent_id uuid NOT NULL,
    child_agent_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: network_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_nodes (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    direct_parent_agent_id uuid,
    status character varying(32) NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: network_snapshot_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_snapshot_nodes (
    snapshot_id uuid NOT NULL,
    ancestor_agent_id uuid NOT NULL,
    depth integer NOT NULL,
    rank_id_at_snapshot uuid
);


--
-- Name: network_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_snapshots (
    organization_id uuid NOT NULL,
    reason character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    organization_id uuid NOT NULL,
    recipient_user_id uuid NOT NULL,
    type character varying(64) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    body character varying(1000),
    is_read boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    product_version_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint NOT NULL,
    credit_debit_transaction_id uuid,
    cashback_requested boolean NOT NULL,
    cashback_surcharge_cents bigint NOT NULL,
    cashback_credited_at timestamp with time zone,
    status character varying(16) NOT NULL,
    payment_method character varying(16) NOT NULL,
    note character varying(1000),
    payment_proof_storage_key character varying(500),
    payment_proof_original_filename character varying(255),
    payment_proof_uploaded_at timestamp with time zone,
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_orders_ck_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_orders_ck_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents))
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    name character varying(255) NOT NULL,
    legal_name character varying(255),
    vat_number character varying(32),
    status character varying(32) NOT NULL,
    settings jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: otp_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.otp_codes (
    user_id uuid NOT NULL,
    purpose character varying(32) NOT NULL,
    code_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    code character varying(64) NOT NULL,
    description character varying(255) NOT NULL,
    id uuid NOT NULL
);


--
-- Name: product_request_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_request_messages (
    request_id uuid NOT NULL,
    author_user_id uuid NOT NULL,
    author_role character varying(32) NOT NULL,
    body text NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: product_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_requests (
    organization_id uuid NOT NULL,
    opened_by_user_id uuid NOT NULL,
    opened_by_role character varying(32) NOT NULL,
    product_name character varying(255) NOT NULL,
    reference_url character varying(1000),
    status character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: product_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_versions (
    product_id uuid NOT NULL,
    version_label character varying(32) NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000) NOT NULL,
    image_url character varying(1000),
    base_price_cents bigint NOT NULL,
    monthly_price_cents bigint,
    initial_fee_cents bigint NOT NULL,
    recurring_fee_cents bigint NOT NULL,
    billing_period character varying(16) NOT NULL,
    contract_duration_months integer,
    tax_configuration jsonb NOT NULL,
    commission_plan_version_id uuid,
    commission_tokens jsonb NOT NULL,
    required_documents jsonb NOT NULL,
    terms_version character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    status character varying(32) NOT NULL,
    credit_discount_percentage integer NOT NULL,
    cashback_enabled boolean NOT NULL,
    contract_cashback_percentage integer NOT NULL,
    first_referrer_bonus_enabled boolean NOT NULL,
    first_referrer_bonus_cents bigint NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    organization_id uuid NOT NULL,
    code character varying(64) NOT NULL,
    product_type character varying(32) NOT NULL,
    customer_type character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    category character varying(16) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: promoter_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.promoter_codes (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    personal_link character varying(500) NOT NULL,
    qr_code_url character varying(500),
    status character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: ranks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ranks (
    organization_id uuid NOT NULL,
    code character varying(16) NOT NULL,
    name character varying(128) NOT NULL,
    level integer NOT NULL,
    personal_token_cents bigint NOT NULL,
    personal_volume_threshold_cents bigint NOT NULL,
    group_volume_threshold_cents bigint NOT NULL,
    evaluation_window_months integer NOT NULL,
    single_branch_cap_percentage numeric(5,2) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    rule_version character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: referral_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_events (
    organization_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    ip_address character varying(64),
    user_agent character varying(255),
    occurred_at timestamp with time zone NOT NULL,
    id uuid NOT NULL
);


--
-- Name: referral_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_sessions (
    organization_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    cookie_token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_permissions (
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    organization_id uuid,
    code character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    user_id uuid NOT NULL,
    refresh_token_hash character varying(64) NOT NULL,
    user_agent character varying(255),
    ip_address character varying(64),
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    replaced_by_session_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: shop_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shop_categories (
    organization_id uuid NOT NULL,
    shop character varying(16) NOT NULL,
    name character varying(120) NOT NULL,
    "position" integer NOT NULL,
    active boolean NOT NULL,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    producer_id uuid
);


--
-- Name: shop_category_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shop_category_products (
    organization_id uuid NOT NULL,
    category_id uuid NOT NULL,
    shop character varying(16) NOT NULL,
    product_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: spend_pins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spend_pins (
    user_id uuid NOT NULL,
    enabled boolean NOT NULL,
    pin_hash character varying(255),
    failed_attempts integer NOT NULL,
    locked_until timestamp with time zone,
    updated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sponsors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sponsors (
    organization_id uuid NOT NULL,
    name character varying(120) NOT NULL,
    slug character varying(80) NOT NULL,
    tagline character varying(200),
    description text,
    logo_url character varying(500),
    website_url character varying(500),
    color character varying(7),
    sort_order smallint DEFAULT 0 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_sponsors_website_url CHECK (((website_url IS NULL) OR ((website_url)::text ~* '^https?://'::text)))
);


--
-- Name: ticket_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticket_messages (
    ticket_id uuid NOT NULL,
    author_user_id uuid NOT NULL,
    author_role character varying(32) NOT NULL,
    body text NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tickets (
    organization_id uuid NOT NULL,
    opened_by_user_id uuid NOT NULL,
    opened_by_role character varying(32) NOT NULL,
    subject character varying(255) NOT NULL,
    category character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    contract_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    role_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    organization_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    status character varying(32) NOT NULL,
    email_verified_at timestamp with time zone,
    failed_login_attempts integer NOT NULL,
    locked_until timestamp with time zone,
    privacy_accepted_at timestamp with time zone,
    fiscal_code character varying(16),
    residence_street character varying(255),
    residence_city character varying(100),
    residence_province character varying(2),
    residence_postal_code character varying(10),
    residence_country character varying(2) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    club_id uuid,
    username character varying(40)
);


--
-- Name: wallet_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallet_transactions (
    organization_id uuid NOT NULL,
    from_wallet_id uuid,
    to_wallet_id uuid,
    amount_cents bigint NOT NULL,
    currency character varying(3) NOT NULL,
    type character varying(16) NOT NULL,
    reference_contract_id uuid,
    source character varying(32),
    reference_order_id uuid,
    reference_jav_market_order_id uuid,
    reverses_transaction_id uuid,
    note character varying(500),
    actor_user_id uuid,
    idempotency_key character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    reference_club_proof_id uuid,
    reference_club_athlete_id uuid,
    CONSTRAINT ck_wallet_transactions_ck_wallet_transactions_has_a_side CHECK (((from_wallet_id IS NOT NULL) OR (to_wallet_id IS NOT NULL)))
);


--
-- Name: wallets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallets (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    address character varying(42) NOT NULL,
    balance_cents bigint NOT NULL,
    currency character varying(3) NOT NULL,
    can_transfer boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_wallets_ck_wallets_balance_non_negative CHECK ((balance_cents >= 0))
);


--
-- Name: belt_exams pk_belt_exams; Type: CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.belt_exams
    ADD CONSTRAINT pk_belt_exams PRIMARY KEY (id);


--
-- Name: careers pk_careers; Type: CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.careers
    ADD CONSTRAINT pk_careers PRIMARY KEY (player_id);


--
-- Name: players pk_players; Type: CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.players
    ADD CONSTRAINT pk_players PRIMARY KEY (id);


--
-- Name: quiz_attempts pk_quiz_attempts; Type: CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.quiz_attempts
    ADD CONSTRAINT pk_quiz_attempts PRIMARY KEY (id);


--
-- Name: belt_exams uq_belt_exams_player_belt; Type: CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.belt_exams
    ADD CONSTRAINT uq_belt_exams_player_belt UNIQUE (player_id, belt);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: addresses pk_addresses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.addresses
    ADD CONSTRAINT pk_addresses PRIMARY KEY (id);


--
-- Name: agent_profiles pk_agent_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT pk_agent_profiles PRIMARY KEY (id);


--
-- Name: agent_rank_history pk_agent_rank_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT pk_agent_rank_history PRIMARY KEY (id);


--
-- Name: attribution_corrections pk_attribution_corrections; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT pk_attribution_corrections PRIMARY KEY (id);


--
-- Name: audit_log pk_audit_log; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT pk_audit_log PRIMARY KEY (id);


--
-- Name: cart_items pk_cart_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT pk_cart_items PRIMARY KEY (id);


--
-- Name: carts pk_carts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carts
    ADD CONSTRAINT pk_carts PRIMARY KEY (id);


--
-- Name: club_applications pk_club_applications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_applications
    ADD CONSTRAINT pk_club_applications PRIMARY KEY (id);


--
-- Name: club_athlete_documents pk_club_athlete_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_documents
    ADD CONSTRAINT pk_club_athlete_documents PRIMARY KEY (id);


--
-- Name: club_athlete_login_codes pk_club_athlete_login_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_login_codes
    ADD CONSTRAINT pk_club_athlete_login_codes PRIMARY KEY (id);


--
-- Name: club_athlete_media pk_club_athlete_media; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_media
    ADD CONSTRAINT pk_club_athlete_media PRIMARY KEY (id);


--
-- Name: club_athlete_public_profiles pk_club_athlete_public_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_public_profiles
    ADD CONSTRAINT pk_club_athlete_public_profiles PRIMARY KEY (id);


--
-- Name: club_athlete_records pk_club_athlete_records; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_records
    ADD CONSTRAINT pk_club_athlete_records PRIMARY KEY (athlete_id);


--
-- Name: club_athlete_supports pk_club_athlete_supports; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_supports
    ADD CONSTRAINT pk_club_athlete_supports PRIMARY KEY (id);


--
-- Name: club_athletes pk_club_athletes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT pk_club_athletes PRIMARY KEY (id);


--
-- Name: club_attendances pk_club_attendances; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT pk_club_attendances PRIMARY KEY (id);


--
-- Name: club_belt_grades pk_club_belt_grades; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_belt_grades
    ADD CONSTRAINT pk_club_belt_grades PRIMARY KEY (id);


--
-- Name: club_change_requests pk_club_change_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_change_requests
    ADD CONSTRAINT pk_club_change_requests PRIMARY KEY (id);


--
-- Name: club_cleaning_logs pk_club_cleaning_logs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_cleaning_logs
    ADD CONSTRAINT pk_club_cleaning_logs PRIMARY KEY (id);


--
-- Name: club_competition_entries pk_club_competition_entries; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT pk_club_competition_entries PRIMARY KEY (id);


--
-- Name: club_competitions pk_club_competitions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competitions
    ADD CONSTRAINT pk_club_competitions PRIMARY KEY (id);


--
-- Name: club_consents pk_club_consents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_consents
    ADD CONSTRAINT pk_club_consents PRIMARY KEY (id);


--
-- Name: club_course_athletes pk_club_course_athletes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_athletes
    ADD CONSTRAINT pk_club_course_athletes PRIMARY KEY (id);


--
-- Name: club_course_slots pk_club_course_slots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_slots
    ADD CONSTRAINT pk_club_course_slots PRIMARY KEY (id);


--
-- Name: club_course_staff pk_club_course_staff; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_staff
    ADD CONSTRAINT pk_club_course_staff PRIMARY KEY (id);


--
-- Name: club_courses pk_club_courses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_courses
    ADD CONSTRAINT pk_club_courses PRIMARY KEY (id);


--
-- Name: club_documents pk_club_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_documents
    ADD CONSTRAINT pk_club_documents PRIMARY KEY (id);


--
-- Name: club_equipment_orders pk_club_equipment_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT pk_club_equipment_orders PRIMARY KEY (id);


--
-- Name: club_expenses pk_club_expenses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_expenses
    ADD CONSTRAINT pk_club_expenses PRIMARY KEY (id);


--
-- Name: club_external_coach_fees pk_club_external_coach_fees; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_external_coach_fees
    ADD CONSTRAINT pk_club_external_coach_fees PRIMARY KEY (id);


--
-- Name: club_fees pk_club_fees; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT pk_club_fees PRIMARY KEY (id);


--
-- Name: club_functions pk_club_functions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT pk_club_functions PRIMARY KEY (id);


--
-- Name: club_medical_certificates pk_club_medical_certificates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_medical_certificates
    ADD CONSTRAINT pk_club_medical_certificates PRIMARY KEY (id);


--
-- Name: club_news_likes pk_club_news_likes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_likes
    ADD CONSTRAINT pk_club_news_likes PRIMARY KEY (post_id, user_id);


--
-- Name: club_news_posts pk_club_news_posts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_posts
    ADD CONSTRAINT pk_club_news_posts PRIMARY KEY (id);


--
-- Name: club_payment_proof_fees pk_club_payment_proof_fees; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proof_fees
    ADD CONSTRAINT pk_club_payment_proof_fees PRIMARY KEY (id);


--
-- Name: club_payment_proofs pk_club_payment_proofs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proofs
    ADD CONSTRAINT pk_club_payment_proofs PRIMARY KEY (id);


--
-- Name: club_plans pk_club_plans; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_plans
    ADD CONSTRAINT pk_club_plans PRIMARY KEY (id);


--
-- Name: club_platform_fees pk_club_platform_fees; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_platform_fees
    ADD CONSTRAINT pk_club_platform_fees PRIMARY KEY (id);


--
-- Name: club_receipt_counters pk_club_receipt_counters; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_receipt_counters
    ADD CONSTRAINT pk_club_receipt_counters PRIMARY KEY (club_id, prefix, year);


--
-- Name: club_recurring_expenses pk_club_recurring_expenses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_recurring_expenses
    ADD CONSTRAINT pk_club_recurring_expenses PRIMARY KEY (id);


--
-- Name: club_referees pk_club_referees; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT pk_club_referees PRIMARY KEY (id);


--
-- Name: club_reminders_sent pk_club_reminders_sent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reminders_sent
    ADD CONSTRAINT pk_club_reminders_sent PRIMARY KEY (id);


--
-- Name: club_reports pk_club_reports; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reports
    ADD CONSTRAINT pk_club_reports PRIMARY KEY (id);


--
-- Name: club_school_letters pk_club_school_letters; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT pk_club_school_letters PRIMARY KEY (id);


--
-- Name: club_sites pk_club_sites; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_sites
    ADD CONSTRAINT pk_club_sites PRIMARY KEY (id);


--
-- Name: club_staff_messages pk_club_staff_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_messages
    ADD CONSTRAINT pk_club_staff_messages PRIMARY KEY (id);


--
-- Name: club_staff_rates pk_club_staff_rates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_rates
    ADD CONSTRAINT pk_club_staff_rates PRIMARY KEY (id);


--
-- Name: club_staff_tasks pk_club_staff_tasks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_tasks
    ADD CONSTRAINT pk_club_staff_tasks PRIMARY KEY (id);


--
-- Name: club_transport_requests pk_club_transport_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_transport_requests
    ADD CONSTRAINT pk_club_transport_requests PRIMARY KEY (id);


--
-- Name: club_work_sessions pk_club_work_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_work_sessions
    ADD CONSTRAINT pk_club_work_sessions PRIMARY KEY (id);


--
-- Name: clubs pk_clubs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clubs
    ADD CONSTRAINT pk_clubs PRIMARY KEY (id);


--
-- Name: commission_adjustments pk_commission_adjustments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT pk_commission_adjustments PRIMARY KEY (id);


--
-- Name: commission_calculation_steps pk_commission_calculation_steps; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculation_steps
    ADD CONSTRAINT pk_commission_calculation_steps PRIMARY KEY (id);


--
-- Name: commission_calculations pk_commission_calculations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT pk_commission_calculations PRIMARY KEY (id);


--
-- Name: commission_movements pk_commission_movements; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT pk_commission_movements PRIMARY KEY (id);


--
-- Name: commission_offsets pk_commission_offsets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT pk_commission_offsets PRIMARY KEY (id);


--
-- Name: commission_plan_versions pk_commission_plan_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_plan_versions
    ADD CONSTRAINT pk_commission_plan_versions PRIMARY KEY (id);


--
-- Name: commission_reversals pk_commission_reversals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT pk_commission_reversals PRIMARY KEY (id);


--
-- Name: commission_rule_versions pk_commission_rule_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_rule_versions
    ADD CONSTRAINT pk_commission_rule_versions PRIMARY KEY (id);


--
-- Name: companies pk_companies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT pk_companies PRIMARY KEY (customer_id);


--
-- Name: contact_messages pk_contact_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_messages
    ADD CONSTRAINT pk_contact_messages PRIMARY KEY (id);


--
-- Name: contract_attributions pk_contract_attributions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT pk_contract_attributions PRIMARY KEY (id);


--
-- Name: contract_commission_plans pk_contract_commission_plans; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_commission_plans
    ADD CONSTRAINT pk_contract_commission_plans PRIMARY KEY (id);


--
-- Name: contract_events pk_contract_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_events
    ADD CONSTRAINT pk_contract_events PRIMARY KEY (id);


--
-- Name: contract_instalments pk_contract_instalments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_instalments
    ADD CONSTRAINT pk_contract_instalments PRIMARY KEY (id);


--
-- Name: contract_requests pk_contract_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT pk_contract_requests PRIMARY KEY (id);


--
-- Name: contract_status_history pk_contract_status_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_status_history
    ADD CONSTRAINT pk_contract_status_history PRIMARY KEY (id);


--
-- Name: contracts pk_contracts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT pk_contracts PRIMARY KEY (id);


--
-- Name: customer_attributions pk_customer_attributions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT pk_customer_attributions PRIMARY KEY (id);


--
-- Name: customer_profiles pk_customer_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT pk_customer_profiles PRIMARY KEY (customer_id);


--
-- Name: customers pk_customers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT pk_customers PRIMARY KEY (id);


--
-- Name: documentation_posts pk_documentation_posts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documentation_posts
    ADD CONSTRAINT pk_documentation_posts PRIMARY KEY (id);


--
-- Name: documents pk_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT pk_documents PRIMARY KEY (id);


--
-- Name: domain_outbox pk_domain_outbox; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_outbox
    ADD CONSTRAINT pk_domain_outbox PRIMARY KEY (id);


--
-- Name: email_template_overrides pk_email_template_overrides; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_template_overrides
    ADD CONSTRAINT pk_email_template_overrides PRIMARY KEY (key);


--
-- Name: email_verification_tokens pk_email_verification_tokens; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT pk_email_verification_tokens PRIMARY KEY (id);


--
-- Name: friend_referral_codes pk_friend_referral_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_codes
    ADD CONSTRAINT pk_friend_referral_codes PRIMARY KEY (id);


--
-- Name: friend_referral_reward_claims pk_friend_referral_reward_claims; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_reward_claims
    ADD CONSTRAINT pk_friend_referral_reward_claims PRIMARY KEY (id);


--
-- Name: friend_referrals pk_friend_referrals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referrals
    ADD CONSTRAINT pk_friend_referrals PRIMARY KEY (id);


--
-- Name: jav_market_order_items pk_jav_market_order_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT pk_jav_market_order_items PRIMARY KEY (id);


--
-- Name: jav_market_orders pk_jav_market_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT pk_jav_market_orders PRIMARY KEY (id);


--
-- Name: jav_market_producers pk_jav_market_producers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_producers
    ADD CONSTRAINT pk_jav_market_producers PRIMARY KEY (id);


--
-- Name: jav_market_products pk_jav_market_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_products
    ADD CONSTRAINT pk_jav_market_products PRIMARY KEY (id);


--
-- Name: jav_market_settings pk_jav_market_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_settings
    ADD CONSTRAINT pk_jav_market_settings PRIMARY KEY (id);


--
-- Name: jav_market_supplier_dispatches pk_jav_market_supplier_dispatches; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_supplier_dispatches
    ADD CONSTRAINT pk_jav_market_supplier_dispatches PRIMARY KEY (id);


--
-- Name: jav_market_variants pk_jav_market_variants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_variants
    ADD CONSTRAINT pk_jav_market_variants PRIMARY KEY (id);


--
-- Name: javbot_conversations pk_javbot_conversations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_conversations
    ADD CONSTRAINT pk_javbot_conversations PRIMARY KEY (id);


--
-- Name: javbot_instructions pk_javbot_instructions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_instructions
    ADD CONSTRAINT pk_javbot_instructions PRIMARY KEY (id);


--
-- Name: javbot_knowledge_chunks pk_javbot_knowledge_chunks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_chunks
    ADD CONSTRAINT pk_javbot_knowledge_chunks PRIMARY KEY (id);


--
-- Name: javbot_knowledge_documents pk_javbot_knowledge_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_documents
    ADD CONSTRAINT pk_javbot_knowledge_documents PRIMARY KEY (id);


--
-- Name: javbot_messages pk_javbot_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_messages
    ADD CONSTRAINT pk_javbot_messages PRIMARY KEY (id);


--
-- Name: javbot_tasks pk_javbot_tasks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_tasks
    ADD CONSTRAINT pk_javbot_tasks PRIMARY KEY (id);


--
-- Name: legacy_import_map pk_legacy_import_map; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_import_map
    ADD CONSTRAINT pk_legacy_import_map PRIMARY KEY (id);


--
-- Name: network_assignment_history pk_network_assignment_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT pk_network_assignment_history PRIMARY KEY (id);


--
-- Name: network_closure pk_network_closure; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT pk_network_closure PRIMARY KEY (organization_id, ancestor_agent_id, descendant_agent_id, effective_from);


--
-- Name: network_edges pk_network_edges; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT pk_network_edges PRIMARY KEY (id);


--
-- Name: network_nodes pk_network_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT pk_network_nodes PRIMARY KEY (id);


--
-- Name: network_snapshot_nodes pk_network_snapshot_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT pk_network_snapshot_nodes PRIMARY KEY (snapshot_id, ancestor_agent_id);


--
-- Name: network_snapshots pk_network_snapshots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshots
    ADD CONSTRAINT pk_network_snapshots PRIMARY KEY (id);


--
-- Name: notifications pk_notifications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT pk_notifications PRIMARY KEY (id);


--
-- Name: orders pk_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT pk_orders PRIMARY KEY (id);


--
-- Name: organizations pk_organizations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT pk_organizations PRIMARY KEY (id);


--
-- Name: otp_codes pk_otp_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.otp_codes
    ADD CONSTRAINT pk_otp_codes PRIMARY KEY (id);


--
-- Name: password_reset_tokens pk_password_reset_tokens; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT pk_password_reset_tokens PRIMARY KEY (id);


--
-- Name: permissions pk_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT pk_permissions PRIMARY KEY (id);


--
-- Name: product_request_messages pk_product_request_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_request_messages
    ADD CONSTRAINT pk_product_request_messages PRIMARY KEY (id);


--
-- Name: product_requests pk_product_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_requests
    ADD CONSTRAINT pk_product_requests PRIMARY KEY (id);


--
-- Name: product_versions pk_product_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_versions
    ADD CONSTRAINT pk_product_versions PRIMARY KEY (id);


--
-- Name: products pk_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT pk_products PRIMARY KEY (id);


--
-- Name: promoter_codes pk_promoter_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promoter_codes
    ADD CONSTRAINT pk_promoter_codes PRIMARY KEY (id);


--
-- Name: ranks pk_ranks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranks
    ADD CONSTRAINT pk_ranks PRIMARY KEY (id);


--
-- Name: referral_events pk_referral_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_events
    ADD CONSTRAINT pk_referral_events PRIMARY KEY (id);


--
-- Name: referral_sessions pk_referral_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_sessions
    ADD CONSTRAINT pk_referral_sessions PRIMARY KEY (id);


--
-- Name: role_permissions pk_role_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_id);


--
-- Name: roles pk_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT pk_roles PRIMARY KEY (id);


--
-- Name: sessions pk_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT pk_sessions PRIMARY KEY (id);


--
-- Name: shop_categories pk_shop_categories; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_categories
    ADD CONSTRAINT pk_shop_categories PRIMARY KEY (id);


--
-- Name: shop_category_products pk_shop_category_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_category_products
    ADD CONSTRAINT pk_shop_category_products PRIMARY KEY (id);


--
-- Name: spend_pins pk_spend_pins; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spend_pins
    ADD CONSTRAINT pk_spend_pins PRIMARY KEY (id);


--
-- Name: sponsors pk_sponsors; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sponsors
    ADD CONSTRAINT pk_sponsors PRIMARY KEY (id);


--
-- Name: ticket_messages pk_ticket_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT pk_ticket_messages PRIMARY KEY (id);


--
-- Name: tickets pk_tickets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT pk_tickets PRIMARY KEY (id);


--
-- Name: user_roles pk_user_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT pk_user_roles PRIMARY KEY (id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: wallet_transactions pk_wallet_transactions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT pk_wallet_transactions PRIMARY KEY (id);


--
-- Name: wallets pk_wallets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT pk_wallets PRIMARY KEY (id);


--
-- Name: agent_profiles uq_agent_promoter_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT uq_agent_promoter_code UNIQUE (organization_id, promoter_code);


--
-- Name: cart_items uq_cart_items_jav_market_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT uq_cart_items_jav_market_variant UNIQUE (cart_id, jav_market_variant_id);


--
-- Name: cart_items uq_cart_items_product_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT uq_cart_items_product_version UNIQUE (cart_id, product_version_id);


--
-- Name: carts uq_carts_customer_shop; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carts
    ADD CONSTRAINT uq_carts_customer_shop UNIQUE (customer_user_id, shop);


--
-- Name: club_athlete_login_codes uq_club_athlete_login_codes_token_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_login_codes
    ADD CONSTRAINT uq_club_athlete_login_codes_token_hash UNIQUE (token_hash);


--
-- Name: club_athlete_media uq_club_athlete_media_athlete_youtube; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_media
    ADD CONSTRAINT uq_club_athlete_media_athlete_youtube UNIQUE (athlete_id, youtube_id);


--
-- Name: club_athlete_public_profiles uq_club_athlete_public_profiles_athlete_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_public_profiles
    ADD CONSTRAINT uq_club_athlete_public_profiles_athlete_id UNIQUE (athlete_id);


--
-- Name: club_athletes uq_club_athletes_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT uq_club_athletes_user_id UNIQUE (user_id);


--
-- Name: club_attendances uq_club_attendances_athlete_course_date; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT uq_club_attendances_athlete_course_date UNIQUE (athlete_id, course_id, date);


--
-- Name: club_belt_grades uq_club_belt_grades_athlete_grade; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_belt_grades
    ADD CONSTRAINT uq_club_belt_grades_athlete_grade UNIQUE (athlete_id, grade);


--
-- Name: club_cleaning_logs uq_club_cleaning_logs_expense_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_cleaning_logs
    ADD CONSTRAINT uq_club_cleaning_logs_expense_id UNIQUE (expense_id);


--
-- Name: club_competition_entries uq_club_competition_entries_competition_athlete; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT uq_club_competition_entries_competition_athlete UNIQUE (competition_id, athlete_id);


--
-- Name: club_course_athletes uq_club_course_athletes_course_athlete; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_athletes
    ADD CONSTRAINT uq_club_course_athletes_course_athlete UNIQUE (course_id, athlete_id);


--
-- Name: club_course_staff uq_club_course_staff_course_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_staff
    ADD CONSTRAINT uq_club_course_staff_course_user UNIQUE (course_id, user_id);


--
-- Name: club_equipment_orders uq_club_equipment_orders_fee_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT uq_club_equipment_orders_fee_id UNIQUE (fee_id);


--
-- Name: club_expenses uq_club_expenses_recurring_period; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_expenses
    ADD CONSTRAINT uq_club_expenses_recurring_period UNIQUE (recurring_id, period);


--
-- Name: club_external_coach_fees uq_club_external_coach_fees_expense_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_external_coach_fees
    ADD CONSTRAINT uq_club_external_coach_fees_expense_id UNIQUE (expense_id);


--
-- Name: club_fees uq_club_fees_athlete_kind_period; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT uq_club_fees_athlete_kind_period UNIQUE (athlete_id, kind, period);


--
-- Name: club_functions uq_club_functions_club_athlete; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT uq_club_functions_club_athlete UNIQUE (club_id, athlete_id);


--
-- Name: club_functions uq_club_functions_club_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT uq_club_functions_club_user UNIQUE (club_id, user_id);


--
-- Name: club_payment_proof_fees uq_club_payment_proof_fees_proof_fee; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proof_fees
    ADD CONSTRAINT uq_club_payment_proof_fees_proof_fee UNIQUE (proof_id, fee_id);


--
-- Name: club_platform_fees uq_club_platform_fees_club_from; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_platform_fees
    ADD CONSTRAINT uq_club_platform_fees_club_from UNIQUE (club_id, valid_from);


--
-- Name: club_referees uq_club_referees_club_athlete; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT uq_club_referees_club_athlete UNIQUE (club_id, athlete_id);


--
-- Name: club_referees uq_club_referees_club_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT uq_club_referees_club_user UNIQUE (club_id, user_id);


--
-- Name: club_reminders_sent uq_club_reminders_sent_kind_entity_stage; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reminders_sent
    ADD CONSTRAINT uq_club_reminders_sent_kind_entity_stage UNIQUE (kind, entity_id, stage);


--
-- Name: club_school_letters uq_club_school_letters_entry_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT uq_club_school_letters_entry_id UNIQUE (entry_id);


--
-- Name: club_sites uq_club_sites_club_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_sites
    ADD CONSTRAINT uq_club_sites_club_id UNIQUE (club_id);


--
-- Name: club_staff_rates uq_club_staff_rates_club_user_from; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_rates
    ADD CONSTRAINT uq_club_staff_rates_club_user_from UNIQUE (club_id, user_id, valid_from);


--
-- Name: club_transport_requests uq_club_transport_requests_competition_club; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_transport_requests
    ADD CONSTRAINT uq_club_transport_requests_competition_club UNIQUE (competition_id, club_id);


--
-- Name: clubs uq_clubs_org_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clubs
    ADD CONSTRAINT uq_clubs_org_slug UNIQUE (organization_id, slug);


--
-- Name: commission_calculations uq_commission_calculations_contract_trigger; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT uq_commission_calculations_contract_trigger UNIQUE (contract_id, trigger_event_id);


--
-- Name: commission_movements uq_commission_movements_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT uq_commission_movements_idempotency_key UNIQUE (idempotency_key);


--
-- Name: contract_commission_plans uq_contract_commission_plans_contract_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_commission_plans
    ADD CONSTRAINT uq_contract_commission_plans_contract_id UNIQUE (contract_id);


--
-- Name: contract_instalments uq_contract_instalments_contract_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_instalments
    ADD CONSTRAINT uq_contract_instalments_contract_number UNIQUE (contract_id, number);


--
-- Name: customers uq_customers_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT uq_customers_user_id UNIQUE (user_id);


--
-- Name: documents uq_documents_storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT uq_documents_storage_key UNIQUE (storage_key);


--
-- Name: friend_referral_reward_claims uq_friend_referral_claim_user_milestone; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_reward_claims
    ADD CONSTRAINT uq_friend_referral_claim_user_milestone UNIQUE (referrer_user_id, milestone);


--
-- Name: friend_referral_codes uq_friend_referral_codes_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_codes
    ADD CONSTRAINT uq_friend_referral_codes_code UNIQUE (code);


--
-- Name: friend_referral_codes uq_friend_referral_codes_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_codes
    ADD CONSTRAINT uq_friend_referral_codes_user_id UNIQUE (user_id);


--
-- Name: friend_referrals uq_friend_referrals_referred_customer_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referrals
    ADD CONSTRAINT uq_friend_referrals_referred_customer_id UNIQUE (referred_customer_id);


--
-- Name: jav_market_order_items uq_jav_market_order_items_variant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT uq_jav_market_order_items_variant UNIQUE (order_id, variant_id);


--
-- Name: jav_market_orders uq_jav_market_orders_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT uq_jav_market_orders_number UNIQUE (number);


--
-- Name: jav_market_producers uq_jav_market_producers_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_producers
    ADD CONSTRAINT uq_jav_market_producers_name UNIQUE (organization_id, name);


--
-- Name: jav_market_settings uq_jav_market_settings_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_settings
    ADD CONSTRAINT uq_jav_market_settings_organization_id UNIQUE (organization_id);


--
-- Name: jav_market_variants uq_jav_market_variants_sku; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_variants
    ADD CONSTRAINT uq_jav_market_variants_sku UNIQUE (product_id, sku);


--
-- Name: javbot_tasks uq_javbot_tasks_result_ref; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_tasks
    ADD CONSTRAINT uq_javbot_tasks_result_ref UNIQUE (result_ref);


--
-- Name: legacy_import_map uq_legacy_import_map_source_row; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_import_map
    ADD CONSTRAINT uq_legacy_import_map_source_row UNIQUE (source, source_table, source_id);


--
-- Name: permissions uq_permissions_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT uq_permissions_code UNIQUE (code);


--
-- Name: ranks uq_ranks_org_code_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranks
    ADD CONSTRAINT uq_ranks_org_code_version UNIQUE (organization_id, code, rule_version);


--
-- Name: roles uq_roles_org_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT uq_roles_org_code UNIQUE (organization_id, code);


--
-- Name: shop_category_products uq_shop_category_products_category_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_category_products
    ADD CONSTRAINT uq_shop_category_products_category_id UNIQUE (category_id, product_id);


--
-- Name: sponsors uq_sponsors_org_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sponsors
    ADD CONSTRAINT uq_sponsors_org_slug UNIQUE (organization_id, slug);


--
-- Name: user_roles uq_user_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT uq_user_roles UNIQUE (user_id, organization_id, role_id);


--
-- Name: users uq_users_org_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_org_email UNIQUE (organization_id, email);


--
-- Name: wallet_transactions uq_wallet_transactions_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT uq_wallet_transactions_idempotency_key UNIQUE (idempotency_key);


--
-- Name: wallets uq_wallets_address; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT uq_wallets_address UNIQUE (address);


--
-- Name: wallets uq_wallets_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT uq_wallets_user_id UNIQUE (user_id);


--
-- Name: ix_game_belt_exams_player_id; Type: INDEX; Schema: game; Owner: -
--

CREATE INDEX ix_game_belt_exams_player_id ON game.belt_exams USING btree (player_id);


--
-- Name: ix_game_players_user_id; Type: INDEX; Schema: game; Owner: -
--

CREATE UNIQUE INDEX ix_game_players_user_id ON game.players USING btree (user_id);


--
-- Name: ix_game_quiz_attempts_player_id; Type: INDEX; Schema: game; Owner: -
--

CREATE INDEX ix_game_quiz_attempts_player_id ON game.quiz_attempts USING btree (player_id);


--
-- Name: ix_game_quiz_attempts_quiz_id; Type: INDEX; Schema: game; Owner: -
--

CREATE INDEX ix_game_quiz_attempts_quiz_id ON game.quiz_attempts USING btree (quiz_id);


--
-- Name: ix_addresses_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_addresses_customer_id ON public.addresses USING btree (customer_id);


--
-- Name: ix_addresses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_addresses_organization_id ON public.addresses USING btree (organization_id);


--
-- Name: ix_agent_profiles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_profiles_organization_id ON public.agent_profiles USING btree (organization_id);


--
-- Name: ix_agent_rank_history_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_rank_history_agent_id ON public.agent_rank_history USING btree (agent_id);


--
-- Name: ix_agent_rank_history_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_rank_history_organization_id ON public.agent_rank_history USING btree (organization_id);


--
-- Name: ix_attribution_corrections_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attribution_corrections_organization_id ON public.attribution_corrections USING btree (organization_id);


--
-- Name: ix_audit_log_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_action ON public.audit_log USING btree (action);


--
-- Name: ix_audit_log_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_correlation_id ON public.audit_log USING btree (correlation_id);


--
-- Name: ix_audit_log_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_organization_id ON public.audit_log USING btree (organization_id);


--
-- Name: ix_cart_items_cart_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cart_items_cart_id ON public.cart_items USING btree (cart_id);


--
-- Name: ix_carts_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_carts_customer_user_id ON public.carts USING btree (customer_user_id);


--
-- Name: ix_carts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_carts_organization_id ON public.carts USING btree (organization_id);


--
-- Name: ix_club_applications_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_applications_club_id ON public.club_applications USING btree (club_id);


--
-- Name: ix_club_applications_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_applications_status ON public.club_applications USING btree (status);


--
-- Name: ix_club_athlete_documents_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_documents_athlete_id ON public.club_athlete_documents USING btree (athlete_id);


--
-- Name: ix_club_athlete_documents_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_documents_club_id ON public.club_athlete_documents USING btree (club_id);


--
-- Name: ix_club_athlete_login_codes_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_login_codes_athlete_id ON public.club_athlete_login_codes USING btree (athlete_id);


--
-- Name: ix_club_athlete_login_codes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_login_codes_organization_id ON public.club_athlete_login_codes USING btree (organization_id);


--
-- Name: ix_club_athlete_media_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_media_athlete_id ON public.club_athlete_media USING btree (athlete_id);


--
-- Name: ix_club_athlete_media_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_media_club_id ON public.club_athlete_media USING btree (club_id);


--
-- Name: ix_club_athlete_media_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_media_organization_id ON public.club_athlete_media USING btree (organization_id);


--
-- Name: ix_club_athlete_public_profiles_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_public_profiles_club_id ON public.club_athlete_public_profiles USING btree (club_id);


--
-- Name: ix_club_athlete_public_profiles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_public_profiles_organization_id ON public.club_athlete_public_profiles USING btree (organization_id);


--
-- Name: ix_club_athlete_records_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_records_club_id ON public.club_athlete_records USING btree (club_id);


--
-- Name: ix_club_athlete_supports_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_supports_athlete_id ON public.club_athlete_supports USING btree (athlete_id);


--
-- Name: ix_club_athlete_supports_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athlete_supports_club_id ON public.club_athlete_supports USING btree (club_id);


--
-- Name: ix_club_athletes_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athletes_club_id ON public.club_athletes USING btree (club_id);


--
-- Name: ix_club_athletes_guardian_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athletes_guardian_user_id ON public.club_athletes USING btree (guardian_user_id);


--
-- Name: ix_club_athletes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athletes_organization_id ON public.club_athletes USING btree (organization_id);


--
-- Name: ix_club_athletes_plan_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athletes_plan_id ON public.club_athletes USING btree (plan_id);


--
-- Name: ix_club_athletes_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_athletes_status ON public.club_athletes USING btree (status);


--
-- Name: ix_club_attendances_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_attendances_athlete_id ON public.club_attendances USING btree (athlete_id);


--
-- Name: ix_club_attendances_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_attendances_club_id ON public.club_attendances USING btree (club_id);


--
-- Name: ix_club_attendances_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_attendances_course_id ON public.club_attendances USING btree (course_id);


--
-- Name: ix_club_attendances_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_attendances_date ON public.club_attendances USING btree (date);


--
-- Name: ix_club_attendances_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_attendances_organization_id ON public.club_attendances USING btree (organization_id);


--
-- Name: ix_club_belt_grades_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_belt_grades_athlete_id ON public.club_belt_grades USING btree (athlete_id);


--
-- Name: ix_club_belt_grades_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_belt_grades_club_id ON public.club_belt_grades USING btree (club_id);


--
-- Name: ix_club_belt_grades_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_belt_grades_organization_id ON public.club_belt_grades USING btree (organization_id);


--
-- Name: ix_club_change_requests_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_change_requests_athlete_id ON public.club_change_requests USING btree (athlete_id);


--
-- Name: ix_club_change_requests_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_change_requests_club_id ON public.club_change_requests USING btree (club_id);


--
-- Name: ix_club_change_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_change_requests_status ON public.club_change_requests USING btree (status);


--
-- Name: ix_club_cleaning_logs_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_cleaning_logs_club_id ON public.club_cleaning_logs USING btree (club_id);


--
-- Name: ix_club_cleaning_logs_performed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_cleaning_logs_performed_at ON public.club_cleaning_logs USING btree (performed_at);


--
-- Name: ix_club_competition_entries_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competition_entries_athlete_id ON public.club_competition_entries USING btree (athlete_id);


--
-- Name: ix_club_competition_entries_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competition_entries_club_id ON public.club_competition_entries USING btree (club_id);


--
-- Name: ix_club_competition_entries_competition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competition_entries_competition_id ON public.club_competition_entries USING btree (competition_id);


--
-- Name: ix_club_competition_entries_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competition_entries_organization_id ON public.club_competition_entries USING btree (organization_id);


--
-- Name: ix_club_competitions_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competitions_club_id ON public.club_competitions USING btree (club_id);


--
-- Name: ix_club_competitions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competitions_organization_id ON public.club_competitions USING btree (organization_id);


--
-- Name: ix_club_competitions_starts_on; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competitions_starts_on ON public.club_competitions USING btree (starts_on);


--
-- Name: ix_club_competitions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_competitions_status ON public.club_competitions USING btree (status);


--
-- Name: ix_club_consents_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_consents_athlete_id ON public.club_consents USING btree (athlete_id);


--
-- Name: ix_club_consents_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_consents_club_id ON public.club_consents USING btree (club_id);


--
-- Name: ix_club_consents_subject; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_consents_subject ON public.club_consents USING btree (kind, user_id, athlete_id, created_at);


--
-- Name: ix_club_consents_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_consents_user_id ON public.club_consents USING btree (user_id);


--
-- Name: ix_club_course_athletes_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_course_athletes_athlete_id ON public.club_course_athletes USING btree (athlete_id);


--
-- Name: ix_club_course_athletes_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_course_athletes_course_id ON public.club_course_athletes USING btree (course_id);


--
-- Name: ix_club_course_slots_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_course_slots_course_id ON public.club_course_slots USING btree (course_id);


--
-- Name: ix_club_course_staff_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_course_staff_course_id ON public.club_course_staff USING btree (course_id);


--
-- Name: ix_club_course_staff_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_course_staff_user_id ON public.club_course_staff USING btree (user_id);


--
-- Name: ix_club_courses_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_courses_club_id ON public.club_courses USING btree (club_id);


--
-- Name: ix_club_courses_instructor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_courses_instructor_user_id ON public.club_courses USING btree (instructor_user_id);


--
-- Name: ix_club_courses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_courses_organization_id ON public.club_courses USING btree (organization_id);


--
-- Name: ix_club_documents_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_documents_club_id ON public.club_documents USING btree (club_id);


--
-- Name: ix_club_documents_expires_on; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_documents_expires_on ON public.club_documents USING btree (expires_on);


--
-- Name: ix_club_equipment_orders_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_equipment_orders_athlete_id ON public.club_equipment_orders USING btree (athlete_id);


--
-- Name: ix_club_equipment_orders_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_equipment_orders_club_id ON public.club_equipment_orders USING btree (club_id);


--
-- Name: ix_club_equipment_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_equipment_orders_status ON public.club_equipment_orders USING btree (status);


--
-- Name: ix_club_expenses_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_expenses_club_id ON public.club_expenses USING btree (club_id);


--
-- Name: ix_club_expenses_club_spent_on; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_expenses_club_spent_on ON public.club_expenses USING btree (club_id, spent_on);


--
-- Name: ix_club_expenses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_expenses_organization_id ON public.club_expenses USING btree (organization_id);


--
-- Name: ix_club_expenses_recurring_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_expenses_recurring_id ON public.club_expenses USING btree (recurring_id);


--
-- Name: ix_club_external_coach_fees_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_external_coach_fees_club_id ON public.club_external_coach_fees USING btree (club_id);


--
-- Name: ix_club_external_coach_fees_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_external_coach_fees_month ON public.club_external_coach_fees USING btree (month);


--
-- Name: ix_club_fees_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_athlete_id ON public.club_fees USING btree (athlete_id);


--
-- Name: ix_club_fees_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_club_id ON public.club_fees USING btree (club_id);


--
-- Name: ix_club_fees_coach_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_coach_user_id ON public.club_fees USING btree (coach_user_id);


--
-- Name: ix_club_fees_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_course_id ON public.club_fees USING btree (course_id);


--
-- Name: ix_club_fees_due_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_due_date ON public.club_fees USING btree (due_date);


--
-- Name: ix_club_fees_guardian_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_guardian_user_id ON public.club_fees USING btree (guardian_user_id);


--
-- Name: ix_club_fees_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_organization_id ON public.club_fees USING btree (organization_id);


--
-- Name: ix_club_fees_paid_via_proof_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_paid_via_proof_id ON public.club_fees USING btree (paid_via_proof_id);


--
-- Name: ix_club_fees_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_fees_status ON public.club_fees USING btree (status);


--
-- Name: ix_club_functions_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_functions_club_id ON public.club_functions USING btree (club_id);


--
-- Name: ix_club_functions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_functions_organization_id ON public.club_functions USING btree (organization_id);


--
-- Name: ix_club_medical_certificates_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_medical_certificates_athlete_id ON public.club_medical_certificates USING btree (athlete_id);


--
-- Name: ix_club_medical_certificates_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_medical_certificates_club_id ON public.club_medical_certificates USING btree (club_id);


--
-- Name: ix_club_medical_certificates_expires_on; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_medical_certificates_expires_on ON public.club_medical_certificates USING btree (expires_on);


--
-- Name: ix_club_medical_certificates_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_medical_certificates_organization_id ON public.club_medical_certificates USING btree (organization_id);


--
-- Name: ix_club_news_posts_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_news_posts_club_id ON public.club_news_posts USING btree (club_id);


--
-- Name: ix_club_payment_proof_fees_fee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_payment_proof_fees_fee_id ON public.club_payment_proof_fees USING btree (fee_id);


--
-- Name: ix_club_payment_proof_fees_proof_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_payment_proof_fees_proof_id ON public.club_payment_proof_fees USING btree (proof_id);


--
-- Name: ix_club_payment_proofs_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_payment_proofs_club_id ON public.club_payment_proofs USING btree (club_id);


--
-- Name: ix_club_payment_proofs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_payment_proofs_organization_id ON public.club_payment_proofs USING btree (organization_id);


--
-- Name: ix_club_payment_proofs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_payment_proofs_status ON public.club_payment_proofs USING btree (status);


--
-- Name: ix_club_payment_proofs_uploaded_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_payment_proofs_uploaded_by_user_id ON public.club_payment_proofs USING btree (uploaded_by_user_id);


--
-- Name: ix_club_plans_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_plans_club_id ON public.club_plans USING btree (club_id);


--
-- Name: ix_club_plans_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_plans_organization_id ON public.club_plans USING btree (organization_id);


--
-- Name: ix_club_platform_fees_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_platform_fees_club_id ON public.club_platform_fees USING btree (club_id);


--
-- Name: ix_club_platform_fees_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_platform_fees_organization_id ON public.club_platform_fees USING btree (organization_id);


--
-- Name: ix_club_recurring_expenses_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_recurring_expenses_club_id ON public.club_recurring_expenses USING btree (club_id);


--
-- Name: ix_club_recurring_expenses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_recurring_expenses_organization_id ON public.club_recurring_expenses USING btree (organization_id);


--
-- Name: ix_club_referees_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_referees_club_id ON public.club_referees USING btree (club_id);


--
-- Name: ix_club_referees_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_referees_organization_id ON public.club_referees USING btree (organization_id);


--
-- Name: ix_club_reminders_sent_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_reminders_sent_organization_id ON public.club_reminders_sent USING btree (organization_id);


--
-- Name: ix_club_reports_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_reports_club_id ON public.club_reports USING btree (club_id);


--
-- Name: ix_club_school_letters_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_school_letters_athlete_id ON public.club_school_letters USING btree (athlete_id);


--
-- Name: ix_club_school_letters_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_school_letters_club_id ON public.club_school_letters USING btree (club_id);


--
-- Name: ix_club_school_letters_competition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_school_letters_competition_id ON public.club_school_letters USING btree (competition_id);


--
-- Name: ix_club_school_letters_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_school_letters_organization_id ON public.club_school_letters USING btree (organization_id);


--
-- Name: ix_club_sites_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_sites_organization_id ON public.club_sites USING btree (organization_id);


--
-- Name: ix_club_staff_messages_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_messages_club_id ON public.club_staff_messages USING btree (club_id);


--
-- Name: ix_club_staff_messages_staff_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_messages_staff_user_id ON public.club_staff_messages USING btree (staff_user_id);


--
-- Name: ix_club_staff_rates_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_rates_club_id ON public.club_staff_rates USING btree (club_id);


--
-- Name: ix_club_staff_rates_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_rates_organization_id ON public.club_staff_rates USING btree (organization_id);


--
-- Name: ix_club_staff_rates_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_rates_user_id ON public.club_staff_rates USING btree (user_id);


--
-- Name: ix_club_staff_tasks_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_tasks_club_id ON public.club_staff_tasks USING btree (club_id);


--
-- Name: ix_club_staff_tasks_done_on; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_tasks_done_on ON public.club_staff_tasks USING btree (done_on);


--
-- Name: ix_club_staff_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_staff_tasks_user_id ON public.club_staff_tasks USING btree (user_id);


--
-- Name: ix_club_transport_requests_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_transport_requests_club_id ON public.club_transport_requests USING btree (club_id);


--
-- Name: ix_club_transport_requests_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_transport_requests_organization_id ON public.club_transport_requests USING btree (organization_id);


--
-- Name: ix_club_work_sessions_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_work_sessions_club_id ON public.club_work_sessions USING btree (club_id);


--
-- Name: ix_club_work_sessions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_work_sessions_organization_id ON public.club_work_sessions USING btree (organization_id);


--
-- Name: ix_club_work_sessions_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_work_sessions_started_at ON public.club_work_sessions USING btree (started_at);


--
-- Name: ix_club_work_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_club_work_sessions_user_id ON public.club_work_sessions USING btree (user_id);


--
-- Name: ix_clubs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clubs_organization_id ON public.clubs USING btree (organization_id);


--
-- Name: ix_commission_adjustments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_adjustments_organization_id ON public.commission_adjustments USING btree (organization_id);


--
-- Name: ix_commission_calculation_steps_calculation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_calculation_steps_calculation_id ON public.commission_calculation_steps USING btree (calculation_id);


--
-- Name: ix_commission_calculations_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_calculations_contract_id ON public.commission_calculations USING btree (contract_id);


--
-- Name: ix_commission_calculations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_calculations_organization_id ON public.commission_calculations USING btree (organization_id);


--
-- Name: ix_commission_movements_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_movements_agent_id ON public.commission_movements USING btree (agent_id);


--
-- Name: ix_commission_movements_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_movements_contract_id ON public.commission_movements USING btree (contract_id);


--
-- Name: ix_commission_movements_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_movements_organization_id ON public.commission_movements USING btree (organization_id);


--
-- Name: ix_commission_offsets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_offsets_organization_id ON public.commission_offsets USING btree (organization_id);


--
-- Name: ix_commission_plan_versions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_plan_versions_organization_id ON public.commission_plan_versions USING btree (organization_id);


--
-- Name: ix_commission_reversals_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_reversals_organization_id ON public.commission_reversals USING btree (organization_id);


--
-- Name: ix_commission_rule_versions_commission_plan_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_rule_versions_commission_plan_version_id ON public.commission_rule_versions USING btree (commission_plan_version_id);


--
-- Name: ix_contact_messages_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_messages_club_id ON public.contact_messages USING btree (club_id);


--
-- Name: ix_contact_messages_ip_hash_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_messages_ip_hash_created_at ON public.contact_messages USING btree (ip_hash, created_at);


--
-- Name: ix_contact_messages_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_messages_organization_id ON public.contact_messages USING btree (organization_id);


--
-- Name: ix_contact_messages_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_messages_status ON public.contact_messages USING btree (status);


--
-- Name: ix_contract_attributions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_attributions_organization_id ON public.contract_attributions USING btree (organization_id);


--
-- Name: ix_contract_commission_plans_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_commission_plans_organization_id ON public.contract_commission_plans USING btree (organization_id);


--
-- Name: ix_contract_events_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_events_contract_id ON public.contract_events USING btree (contract_id);


--
-- Name: ix_contract_instalments_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_instalments_contract_id ON public.contract_instalments USING btree (contract_id);


--
-- Name: ix_contract_instalments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_instalments_organization_id ON public.contract_instalments USING btree (organization_id);


--
-- Name: ix_contract_requests_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_requests_customer_id ON public.contract_requests USING btree (customer_id);


--
-- Name: ix_contract_requests_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_requests_organization_id ON public.contract_requests USING btree (organization_id);


--
-- Name: ix_contract_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_requests_status ON public.contract_requests USING btree (status);


--
-- Name: ix_contract_status_history_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_status_history_contract_id ON public.contract_status_history USING btree (contract_id);


--
-- Name: ix_contracts_contract_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_contract_request_id ON public.contracts USING btree (contract_request_id);


--
-- Name: ix_contracts_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_customer_id ON public.contracts USING btree (customer_id);


--
-- Name: ix_contracts_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_expires_at ON public.contracts USING btree (expires_at);


--
-- Name: ix_contracts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_organization_id ON public.contracts USING btree (organization_id);


--
-- Name: ix_contracts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_status ON public.contracts USING btree (status);


--
-- Name: ix_customer_attributions_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_attributions_customer_id ON public.customer_attributions USING btree (customer_id);


--
-- Name: ix_customer_attributions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_attributions_organization_id ON public.customer_attributions USING btree (organization_id);


--
-- Name: ix_customers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_organization_id ON public.customers USING btree (organization_id);


--
-- Name: ix_documentation_posts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documentation_posts_organization_id ON public.documentation_posts USING btree (organization_id);


--
-- Name: ix_documentation_posts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documentation_posts_status ON public.documentation_posts USING btree (status);


--
-- Name: ix_documents_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_contract_id ON public.documents USING btree (contract_id);


--
-- Name: ix_documents_contract_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_contract_request_id ON public.documents USING btree (contract_request_id);


--
-- Name: ix_documents_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_organization_id ON public.documents USING btree (organization_id);


--
-- Name: ix_documents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_status ON public.documents USING btree (status);


--
-- Name: ix_domain_outbox_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_outbox_event_type ON public.domain_outbox USING btree (event_type);


--
-- Name: ix_domain_outbox_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_outbox_organization_id ON public.domain_outbox USING btree (organization_id);


--
-- Name: ix_domain_outbox_processed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_outbox_processed_at ON public.domain_outbox USING btree (processed_at);


--
-- Name: ix_email_verification_tokens_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_email_verification_tokens_token_hash ON public.email_verification_tokens USING btree (token_hash);


--
-- Name: ix_email_verification_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_email_verification_tokens_user_id ON public.email_verification_tokens USING btree (user_id);


--
-- Name: ix_friend_referral_codes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friend_referral_codes_organization_id ON public.friend_referral_codes USING btree (organization_id);


--
-- Name: ix_friend_referral_reward_claims_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friend_referral_reward_claims_organization_id ON public.friend_referral_reward_claims USING btree (organization_id);


--
-- Name: ix_friend_referral_reward_claims_referrer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friend_referral_reward_claims_referrer_user_id ON public.friend_referral_reward_claims USING btree (referrer_user_id);


--
-- Name: ix_friend_referral_reward_claims_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friend_referral_reward_claims_status ON public.friend_referral_reward_claims USING btree (status);


--
-- Name: ix_friend_referrals_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friend_referrals_organization_id ON public.friend_referrals USING btree (organization_id);


--
-- Name: ix_friend_referrals_referrer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_friend_referrals_referrer_user_id ON public.friend_referrals USING btree (referrer_user_id);


--
-- Name: ix_jav_market_order_items_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_order_items_order_id ON public.jav_market_order_items USING btree (order_id);


--
-- Name: ix_jav_market_order_items_producer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_order_items_producer_id ON public.jav_market_order_items USING btree (producer_id);


--
-- Name: ix_jav_market_order_items_supplier_dispatch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_order_items_supplier_dispatch_id ON public.jav_market_order_items USING btree (supplier_dispatch_id);


--
-- Name: ix_jav_market_orders_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_orders_athlete_id ON public.jav_market_orders USING btree (athlete_id);


--
-- Name: ix_jav_market_orders_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_orders_club_id ON public.jav_market_orders USING btree (club_id);


--
-- Name: ix_jav_market_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_orders_customer_user_id ON public.jav_market_orders USING btree (customer_user_id);


--
-- Name: ix_jav_market_orders_fulfillment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_orders_fulfillment_status ON public.jav_market_orders USING btree (fulfillment_status);


--
-- Name: ix_jav_market_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_orders_organization_id ON public.jav_market_orders USING btree (organization_id);


--
-- Name: ix_jav_market_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_orders_status ON public.jav_market_orders USING btree (status);


--
-- Name: ix_jav_market_producers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_producers_organization_id ON public.jav_market_producers USING btree (organization_id);


--
-- Name: ix_jav_market_products_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_products_club_id ON public.jav_market_products USING btree (club_id);


--
-- Name: ix_jav_market_products_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_products_organization_id ON public.jav_market_products USING btree (organization_id);


--
-- Name: ix_jav_market_products_producer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_products_producer_id ON public.jav_market_products USING btree (producer_id);


--
-- Name: ix_jav_market_products_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_products_status ON public.jav_market_products USING btree (status);


--
-- Name: ix_jav_market_settings_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_settings_organization_id ON public.jav_market_settings USING btree (organization_id);


--
-- Name: ix_jav_market_supplier_dispatches_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_supplier_dispatches_organization_id ON public.jav_market_supplier_dispatches USING btree (organization_id);


--
-- Name: ix_jav_market_supplier_dispatches_producer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_supplier_dispatches_producer_id ON public.jav_market_supplier_dispatches USING btree (producer_id);


--
-- Name: ix_jav_market_variants_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jav_market_variants_product_id ON public.jav_market_variants USING btree (product_id);


--
-- Name: ix_javbot_conversations_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_conversations_club_id ON public.javbot_conversations USING btree (club_id);


--
-- Name: ix_javbot_conversations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_conversations_organization_id ON public.javbot_conversations USING btree (organization_id);


--
-- Name: ix_javbot_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_conversations_user_id ON public.javbot_conversations USING btree (user_id);


--
-- Name: ix_javbot_knowledge_chunks_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_knowledge_chunks_club_id ON public.javbot_knowledge_chunks USING btree (club_id);


--
-- Name: ix_javbot_knowledge_chunks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_knowledge_chunks_document_id ON public.javbot_knowledge_chunks USING btree (document_id);


--
-- Name: ix_javbot_knowledge_chunks_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_knowledge_chunks_search ON public.javbot_knowledge_chunks USING gin (to_tsvector('simple'::regconfig, norm));


--
-- Name: ix_javbot_knowledge_documents_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_knowledge_documents_club_id ON public.javbot_knowledge_documents USING btree (club_id);


--
-- Name: ix_javbot_knowledge_documents_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_knowledge_documents_organization_id ON public.javbot_knowledge_documents USING btree (organization_id);


--
-- Name: ix_javbot_messages_conversation_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_messages_conversation_created ON public.javbot_messages USING btree (conversation_id, created_at);


--
-- Name: ix_javbot_messages_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_messages_user_id ON public.javbot_messages USING btree (user_id);


--
-- Name: ix_javbot_tasks_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_tasks_conversation_id ON public.javbot_tasks USING btree (conversation_id);


--
-- Name: ix_javbot_tasks_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_tasks_organization_id ON public.javbot_tasks USING btree (organization_id);


--
-- Name: ix_javbot_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_javbot_tasks_user_id ON public.javbot_tasks USING btree (user_id);


--
-- Name: ix_legacy_import_map_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_legacy_import_map_target_id ON public.legacy_import_map USING btree (target_id);


--
-- Name: ix_network_assignment_history_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_assignment_history_organization_id ON public.network_assignment_history USING btree (organization_id);


--
-- Name: ix_network_closure_org_ancestor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_ancestor ON public.network_closure USING btree (organization_id, ancestor_agent_id);


--
-- Name: ix_network_closure_org_ancestor_depth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_ancestor_depth ON public.network_closure USING btree (organization_id, ancestor_agent_id, depth);


--
-- Name: ix_network_closure_org_descendant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_descendant ON public.network_closure USING btree (organization_id, descendant_agent_id);


--
-- Name: ix_network_closure_org_descendant_depth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_descendant_depth ON public.network_closure USING btree (organization_id, descendant_agent_id, depth);


--
-- Name: ix_network_edges_child_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_edges_child_agent_id ON public.network_edges USING btree (child_agent_id);


--
-- Name: ix_network_edges_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_edges_organization_id ON public.network_edges USING btree (organization_id);


--
-- Name: ix_network_edges_parent_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_edges_parent_agent_id ON public.network_edges USING btree (parent_agent_id);


--
-- Name: ix_network_nodes_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_nodes_agent_id ON public.network_nodes USING btree (agent_id);


--
-- Name: ix_network_nodes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_nodes_organization_id ON public.network_nodes USING btree (organization_id);


--
-- Name: ix_network_snapshots_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_snapshots_organization_id ON public.network_snapshots USING btree (organization_id);


--
-- Name: ix_notifications_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_is_read ON public.notifications USING btree (is_read);


--
-- Name: ix_notifications_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_organization_id ON public.notifications USING btree (organization_id);


--
-- Name: ix_notifications_recipient_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_recipient_user_id ON public.notifications USING btree (recipient_user_id);


--
-- Name: ix_notifications_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_type ON public.notifications USING btree (type);


--
-- Name: ix_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_customer_user_id ON public.orders USING btree (customer_user_id);


--
-- Name: ix_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_organization_id ON public.orders USING btree (organization_id);


--
-- Name: ix_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_status ON public.orders USING btree (status);


--
-- Name: ix_otp_codes_code_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_otp_codes_code_hash ON public.otp_codes USING btree (code_hash);


--
-- Name: ix_otp_codes_purpose; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_otp_codes_purpose ON public.otp_codes USING btree (purpose);


--
-- Name: ix_otp_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_otp_codes_user_id ON public.otp_codes USING btree (user_id);


--
-- Name: ix_password_reset_tokens_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON public.password_reset_tokens USING btree (token_hash);


--
-- Name: ix_password_reset_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_tokens_user_id ON public.password_reset_tokens USING btree (user_id);


--
-- Name: ix_product_request_messages_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_request_messages_request_id ON public.product_request_messages USING btree (request_id);


--
-- Name: ix_product_requests_opened_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_requests_opened_by_user_id ON public.product_requests USING btree (opened_by_user_id);


--
-- Name: ix_product_requests_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_requests_organization_id ON public.product_requests USING btree (organization_id);


--
-- Name: ix_product_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_requests_status ON public.product_requests USING btree (status);


--
-- Name: ix_product_versions_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_versions_product_id ON public.product_versions USING btree (product_id);


--
-- Name: ix_products_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_organization_id ON public.products USING btree (organization_id);


--
-- Name: ix_promoter_codes_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_promoter_codes_agent_id ON public.promoter_codes USING btree (agent_id);


--
-- Name: ix_promoter_codes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_promoter_codes_code ON public.promoter_codes USING btree (code);


--
-- Name: ix_promoter_codes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_promoter_codes_organization_id ON public.promoter_codes USING btree (organization_id);


--
-- Name: ix_ranks_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ranks_organization_id ON public.ranks USING btree (organization_id);


--
-- Name: ix_referral_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_events_organization_id ON public.referral_events USING btree (organization_id);


--
-- Name: ix_referral_events_promoter_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_events_promoter_code_id ON public.referral_events USING btree (promoter_code_id);


--
-- Name: ix_referral_sessions_cookie_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_referral_sessions_cookie_token_hash ON public.referral_sessions USING btree (cookie_token_hash);


--
-- Name: ix_referral_sessions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_sessions_organization_id ON public.referral_sessions USING btree (organization_id);


--
-- Name: ix_referral_sessions_promoter_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_sessions_promoter_code_id ON public.referral_sessions USING btree (promoter_code_id);


--
-- Name: ix_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roles_organization_id ON public.roles USING btree (organization_id);


--
-- Name: ix_sessions_refresh_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sessions_refresh_token_hash ON public.sessions USING btree (refresh_token_hash);


--
-- Name: ix_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sessions_user_id ON public.sessions USING btree (user_id);


--
-- Name: ix_shop_categories_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shop_categories_organization_id ON public.shop_categories USING btree (organization_id);


--
-- Name: ix_shop_categories_producer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shop_categories_producer_id ON public.shop_categories USING btree (producer_id);


--
-- Name: ix_shop_category_products_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shop_category_products_category_id ON public.shop_category_products USING btree (category_id);


--
-- Name: ix_shop_category_products_organization_id_shop_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shop_category_products_organization_id_shop_product_id ON public.shop_category_products USING btree (organization_id, shop, product_id);


--
-- Name: ix_spend_pins_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_spend_pins_user_id ON public.spend_pins USING btree (user_id);


--
-- Name: ix_sponsors_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sponsors_organization_id ON public.sponsors USING btree (organization_id);


--
-- Name: ix_ticket_messages_ticket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ticket_messages_ticket_id ON public.ticket_messages USING btree (ticket_id);


--
-- Name: ix_tickets_opened_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_opened_by_user_id ON public.tickets USING btree (opened_by_user_id);


--
-- Name: ix_tickets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_organization_id ON public.tickets USING btree (organization_id);


--
-- Name: ix_tickets_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_status ON public.tickets USING btree (status);


--
-- Name: ix_user_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_roles_organization_id ON public.user_roles USING btree (organization_id);


--
-- Name: ix_user_roles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_roles_user_id ON public.user_roles USING btree (user_id);


--
-- Name: ix_users_club_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_club_id ON public.users USING btree (club_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_organization_id ON public.users USING btree (organization_id);


--
-- Name: ix_wallet_transactions_from_wallet_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_from_wallet_id ON public.wallet_transactions USING btree (from_wallet_id);


--
-- Name: ix_wallet_transactions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_organization_id ON public.wallet_transactions USING btree (organization_id);


--
-- Name: ix_wallet_transactions_reference_club_athlete_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_reference_club_athlete_id ON public.wallet_transactions USING btree (reference_club_athlete_id);


--
-- Name: ix_wallet_transactions_reference_club_proof_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_reference_club_proof_id ON public.wallet_transactions USING btree (reference_club_proof_id);


--
-- Name: ix_wallet_transactions_reference_jav_market_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_reference_jav_market_order_id ON public.wallet_transactions USING btree (reference_jav_market_order_id);


--
-- Name: ix_wallet_transactions_to_wallet_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_to_wallet_id ON public.wallet_transactions USING btree (to_wallet_id);


--
-- Name: ix_wallet_transactions_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_type ON public.wallet_transactions USING btree (type);


--
-- Name: ix_wallets_address; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_address ON public.wallets USING btree (address);


--
-- Name: ix_wallets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_organization_id ON public.wallets USING btree (organization_id);


--
-- Name: ix_wallets_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_user_id ON public.wallets USING btree (user_id);


--
-- Name: uq_club_athletes_club_member_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_club_athletes_club_member_number ON public.club_athletes USING btree (club_id, member_number) WHERE (member_number IS NOT NULL);


--
-- Name: uq_club_athletes_one_self_per_guardian; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_club_athletes_one_self_per_guardian ON public.club_athletes USING btree (guardian_user_id) WHERE is_self;


--
-- Name: uq_club_fees_guardian_membership; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_club_fees_guardian_membership ON public.club_fees USING btree (club_id, guardian_user_id, period) WHERE ((kind)::text = 'MEMBERSHIP'::text);


--
-- Name: uq_club_payment_proofs_club_receipt; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_club_payment_proofs_club_receipt ON public.club_payment_proofs USING btree (club_id, receipt_number) WHERE (receipt_number IS NOT NULL);


--
-- Name: uq_club_work_sessions_one_open; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_club_work_sessions_one_open ON public.club_work_sessions USING btree (user_id) WHERE (ended_at IS NULL);


--
-- Name: uq_clubs_one_jav_courses_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_clubs_one_jav_courses_unit ON public.clubs USING btree (organization_id) WHERE ((kind)::text = 'JAV_COURSES'::text);


--
-- Name: uq_javbot_instructions_club; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_javbot_instructions_club ON public.javbot_instructions USING btree (club_id) WHERE (club_id IS NOT NULL);


--
-- Name: uq_javbot_instructions_common; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_javbot_instructions_common ON public.javbot_instructions USING btree (organization_id) WHERE (club_id IS NULL);


--
-- Name: uq_network_nodes_active_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_network_nodes_active_agent ON public.network_nodes USING btree (organization_id, agent_id) WHERE (effective_to IS NULL);


--
-- Name: uq_shop_categories_organization_id_shop_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_shop_categories_organization_id_shop_name ON public.shop_categories USING btree (organization_id, shop, lower((name)::text));


--
-- Name: uq_users_org_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_org_username ON public.users USING btree (organization_id, username) WHERE (username IS NOT NULL);


--
-- Name: belt_exams fk_belt_exams_player_id_players; Type: FK CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.belt_exams
    ADD CONSTRAINT fk_belt_exams_player_id_players FOREIGN KEY (player_id) REFERENCES game.players(id) ON DELETE CASCADE;


--
-- Name: careers fk_careers_player_id_players; Type: FK CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.careers
    ADD CONSTRAINT fk_careers_player_id_players FOREIGN KEY (player_id) REFERENCES game.players(id) ON DELETE CASCADE;


--
-- Name: quiz_attempts fk_quiz_attempts_player_id_players; Type: FK CONSTRAINT; Schema: game; Owner: -
--

ALTER TABLE ONLY game.quiz_attempts
    ADD CONSTRAINT fk_quiz_attempts_player_id_players FOREIGN KEY (player_id) REFERENCES game.players(id) ON DELETE CASCADE;


--
-- Name: addresses fk_addresses_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.addresses
    ADD CONSTRAINT fk_addresses_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: addresses fk_addresses_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.addresses
    ADD CONSTRAINT fk_addresses_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: agent_profiles fk_agent_profiles_approved_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_approved_by_user_id_users FOREIGN KEY (approved_by_user_id) REFERENCES public.users(id);


--
-- Name: agent_profiles fk_agent_profiles_current_rank_id_ranks; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_current_rank_id_ranks FOREIGN KEY (current_rank_id) REFERENCES public.ranks(id);


--
-- Name: agent_profiles fk_agent_profiles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: agent_profiles fk_agent_profiles_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: agent_rank_history fk_agent_rank_history_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: agent_rank_history fk_agent_rank_history_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: agent_rank_history fk_agent_rank_history_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: agent_rank_history fk_agent_rank_history_rank_id_ranks; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_rank_id_ranks FOREIGN KEY (rank_id) REFERENCES public.ranks(id);


--
-- Name: attribution_corrections fk_attribution_corrections_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: attribution_corrections fk_attribution_corrections_customer_attribution_id_cust_9fdb; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_customer_attribution_id_cust_9fdb FOREIGN KEY (customer_attribution_id) REFERENCES public.customer_attributions(id);


--
-- Name: attribution_corrections fk_attribution_corrections_new_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_new_promoter_code_id_promoter_codes FOREIGN KEY (new_promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: attribution_corrections fk_attribution_corrections_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: attribution_corrections fk_attribution_corrections_previous_promoter_code_id_pr_9ca1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_previous_promoter_code_id_pr_9ca1 FOREIGN KEY (previous_promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: attribution_corrections fk_attribution_corrections_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: audit_log fk_audit_log_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT fk_audit_log_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: audit_log fk_audit_log_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT fk_audit_log_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: cart_items fk_cart_items_cart_id_carts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT fk_cart_items_cart_id_carts FOREIGN KEY (cart_id) REFERENCES public.carts(id) ON DELETE CASCADE;


--
-- Name: cart_items fk_cart_items_jav_market_variant_id_jav_market_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT fk_cart_items_jav_market_variant_id_jav_market_variants FOREIGN KEY (jav_market_variant_id) REFERENCES public.jav_market_variants(id) ON DELETE CASCADE;


--
-- Name: cart_items fk_cart_items_product_version_id_product_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT fk_cart_items_product_version_id_product_versions FOREIGN KEY (product_version_id) REFERENCES public.product_versions(id) ON DELETE CASCADE;


--
-- Name: carts fk_carts_customer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carts
    ADD CONSTRAINT fk_carts_customer_user_id_users FOREIGN KEY (customer_user_id) REFERENCES public.users(id);


--
-- Name: carts fk_carts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carts
    ADD CONSTRAINT fk_carts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_applications fk_club_applications_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_applications
    ADD CONSTRAINT fk_club_applications_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_applications fk_club_applications_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_applications
    ADD CONSTRAINT fk_club_applications_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_applications fk_club_applications_decided_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_applications
    ADD CONSTRAINT fk_club_applications_decided_by_user_id_users FOREIGN KEY (decided_by_user_id) REFERENCES public.users(id);


--
-- Name: club_applications fk_club_applications_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_applications
    ADD CONSTRAINT fk_club_applications_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_documents fk_club_athlete_documents_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_documents
    ADD CONSTRAINT fk_club_athlete_documents_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_athlete_documents fk_club_athlete_documents_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_documents
    ADD CONSTRAINT fk_club_athlete_documents_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_athlete_documents fk_club_athlete_documents_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_documents
    ADD CONSTRAINT fk_club_athlete_documents_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_documents fk_club_athlete_documents_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_documents
    ADD CONSTRAINT fk_club_athlete_documents_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_athlete_login_codes fk_club_athlete_login_codes_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_login_codes
    ADD CONSTRAINT fk_club_athlete_login_codes_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_athlete_login_codes fk_club_athlete_login_codes_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_login_codes
    ADD CONSTRAINT fk_club_athlete_login_codes_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_athlete_login_codes fk_club_athlete_login_codes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_login_codes
    ADD CONSTRAINT fk_club_athlete_login_codes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_media fk_club_athlete_media_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_media
    ADD CONSTRAINT fk_club_athlete_media_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_athlete_media fk_club_athlete_media_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_media
    ADD CONSTRAINT fk_club_athlete_media_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_athlete_media fk_club_athlete_media_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_media
    ADD CONSTRAINT fk_club_athlete_media_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_athlete_media fk_club_athlete_media_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_media
    ADD CONSTRAINT fk_club_athlete_media_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_public_profiles fk_club_athlete_public_profiles_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_public_profiles
    ADD CONSTRAINT fk_club_athlete_public_profiles_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_athlete_public_profiles fk_club_athlete_public_profiles_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_public_profiles
    ADD CONSTRAINT fk_club_athlete_public_profiles_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_athlete_public_profiles fk_club_athlete_public_profiles_consent_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_public_profiles
    ADD CONSTRAINT fk_club_athlete_public_profiles_consent_by_user_id_users FOREIGN KEY (consent_by_user_id) REFERENCES public.users(id);


--
-- Name: club_athlete_public_profiles fk_club_athlete_public_profiles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_public_profiles
    ADD CONSTRAINT fk_club_athlete_public_profiles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_records fk_club_athlete_records_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_records
    ADD CONSTRAINT fk_club_athlete_records_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id) ON DELETE CASCADE;


--
-- Name: club_athlete_records fk_club_athlete_records_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_records
    ADD CONSTRAINT fk_club_athlete_records_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_athlete_records fk_club_athlete_records_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_records
    ADD CONSTRAINT fk_club_athlete_records_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_records fk_club_athlete_records_updated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_records
    ADD CONSTRAINT fk_club_athlete_records_updated_by_user_id_users FOREIGN KEY (updated_by_user_id) REFERENCES public.users(id);


--
-- Name: club_athlete_supports fk_club_athlete_supports_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_supports
    ADD CONSTRAINT fk_club_athlete_supports_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_athlete_supports fk_club_athlete_supports_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_supports
    ADD CONSTRAINT fk_club_athlete_supports_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_athlete_supports fk_club_athlete_supports_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_supports
    ADD CONSTRAINT fk_club_athlete_supports_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athlete_supports fk_club_athlete_supports_recorded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athlete_supports
    ADD CONSTRAINT fk_club_athlete_supports_recorded_by_user_id_users FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_athletes fk_club_athletes_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT fk_club_athletes_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_athletes fk_club_athletes_guardian_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT fk_club_athletes_guardian_user_id_users FOREIGN KEY (guardian_user_id) REFERENCES public.users(id);


--
-- Name: club_athletes fk_club_athletes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT fk_club_athletes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_athletes fk_club_athletes_plan_id_club_plans; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT fk_club_athletes_plan_id_club_plans FOREIGN KEY (plan_id) REFERENCES public.club_plans(id);


--
-- Name: club_athletes fk_club_athletes_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_athletes
    ADD CONSTRAINT fk_club_athletes_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_attendances fk_club_attendances_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT fk_club_attendances_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_attendances fk_club_attendances_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT fk_club_attendances_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_attendances fk_club_attendances_course_id_club_courses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT fk_club_attendances_course_id_club_courses FOREIGN KEY (course_id) REFERENCES public.club_courses(id) ON DELETE CASCADE;


--
-- Name: club_attendances fk_club_attendances_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT fk_club_attendances_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_attendances fk_club_attendances_recorded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_attendances
    ADD CONSTRAINT fk_club_attendances_recorded_by_user_id_users FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_belt_grades fk_club_belt_grades_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_belt_grades
    ADD CONSTRAINT fk_club_belt_grades_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_belt_grades fk_club_belt_grades_awarded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_belt_grades
    ADD CONSTRAINT fk_club_belt_grades_awarded_by_user_id_users FOREIGN KEY (awarded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_belt_grades fk_club_belt_grades_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_belt_grades
    ADD CONSTRAINT fk_club_belt_grades_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_belt_grades fk_club_belt_grades_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_belt_grades
    ADD CONSTRAINT fk_club_belt_grades_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_change_requests fk_club_change_requests_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_change_requests
    ADD CONSTRAINT fk_club_change_requests_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_change_requests fk_club_change_requests_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_change_requests
    ADD CONSTRAINT fk_club_change_requests_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_change_requests fk_club_change_requests_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_change_requests
    ADD CONSTRAINT fk_club_change_requests_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_change_requests fk_club_change_requests_requested_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_change_requests
    ADD CONSTRAINT fk_club_change_requests_requested_by_user_id_users FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id);


--
-- Name: club_change_requests fk_club_change_requests_resolved_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_change_requests
    ADD CONSTRAINT fk_club_change_requests_resolved_by_user_id_users FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id);


--
-- Name: club_cleaning_logs fk_club_cleaning_logs_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_cleaning_logs
    ADD CONSTRAINT fk_club_cleaning_logs_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_cleaning_logs fk_club_cleaning_logs_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_cleaning_logs
    ADD CONSTRAINT fk_club_cleaning_logs_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_cleaning_logs fk_club_cleaning_logs_expense_id_club_expenses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_cleaning_logs
    ADD CONSTRAINT fk_club_cleaning_logs_expense_id_club_expenses FOREIGN KEY (expense_id) REFERENCES public.club_expenses(id);


--
-- Name: club_cleaning_logs fk_club_cleaning_logs_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_cleaning_logs
    ADD CONSTRAINT fk_club_cleaning_logs_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_competition_entries fk_club_competition_entries_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT fk_club_competition_entries_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_competition_entries fk_club_competition_entries_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT fk_club_competition_entries_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_competition_entries fk_club_competition_entries_competition_id_club_competitions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT fk_club_competition_entries_competition_id_club_competitions FOREIGN KEY (competition_id) REFERENCES public.club_competitions(id);


--
-- Name: club_competition_entries fk_club_competition_entries_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT fk_club_competition_entries_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_competition_entries fk_club_competition_entries_registered_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competition_entries
    ADD CONSTRAINT fk_club_competition_entries_registered_by_user_id_users FOREIGN KEY (registered_by_user_id) REFERENCES public.users(id);


--
-- Name: club_competitions fk_club_competitions_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competitions
    ADD CONSTRAINT fk_club_competitions_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_competitions fk_club_competitions_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competitions
    ADD CONSTRAINT fk_club_competitions_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_competitions fk_club_competitions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_competitions
    ADD CONSTRAINT fk_club_competitions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_consents fk_club_consents_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_consents
    ADD CONSTRAINT fk_club_consents_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_consents fk_club_consents_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_consents
    ADD CONSTRAINT fk_club_consents_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_consents fk_club_consents_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_consents
    ADD CONSTRAINT fk_club_consents_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_consents fk_club_consents_recorded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_consents
    ADD CONSTRAINT fk_club_consents_recorded_by_user_id_users FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_consents fk_club_consents_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_consents
    ADD CONSTRAINT fk_club_consents_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_course_athletes fk_club_course_athletes_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_athletes
    ADD CONSTRAINT fk_club_course_athletes_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_course_athletes fk_club_course_athletes_course_id_club_courses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_athletes
    ADD CONSTRAINT fk_club_course_athletes_course_id_club_courses FOREIGN KEY (course_id) REFERENCES public.club_courses(id) ON DELETE CASCADE;


--
-- Name: club_course_slots fk_club_course_slots_course_id_club_courses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_slots
    ADD CONSTRAINT fk_club_course_slots_course_id_club_courses FOREIGN KEY (course_id) REFERENCES public.club_courses(id) ON DELETE CASCADE;


--
-- Name: club_course_staff fk_club_course_staff_course_id_club_courses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_staff
    ADD CONSTRAINT fk_club_course_staff_course_id_club_courses FOREIGN KEY (course_id) REFERENCES public.club_courses(id) ON DELETE CASCADE;


--
-- Name: club_course_staff fk_club_course_staff_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_course_staff
    ADD CONSTRAINT fk_club_course_staff_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_courses fk_club_courses_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_courses
    ADD CONSTRAINT fk_club_courses_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_courses fk_club_courses_instructor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_courses
    ADD CONSTRAINT fk_club_courses_instructor_user_id_users FOREIGN KEY (instructor_user_id) REFERENCES public.users(id);


--
-- Name: club_courses fk_club_courses_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_courses
    ADD CONSTRAINT fk_club_courses_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_documents fk_club_documents_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_documents
    ADD CONSTRAINT fk_club_documents_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_documents fk_club_documents_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_documents
    ADD CONSTRAINT fk_club_documents_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_documents fk_club_documents_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_documents
    ADD CONSTRAINT fk_club_documents_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_equipment_orders fk_club_equipment_orders_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT fk_club_equipment_orders_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_equipment_orders fk_club_equipment_orders_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT fk_club_equipment_orders_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_equipment_orders fk_club_equipment_orders_fee_id_club_fees; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT fk_club_equipment_orders_fee_id_club_fees FOREIGN KEY (fee_id) REFERENCES public.club_fees(id);


--
-- Name: club_equipment_orders fk_club_equipment_orders_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT fk_club_equipment_orders_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_equipment_orders fk_club_equipment_orders_requested_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_equipment_orders
    ADD CONSTRAINT fk_club_equipment_orders_requested_by_user_id_users FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id);


--
-- Name: club_expenses fk_club_expenses_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_expenses
    ADD CONSTRAINT fk_club_expenses_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_expenses fk_club_expenses_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_expenses
    ADD CONSTRAINT fk_club_expenses_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_expenses fk_club_expenses_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_expenses
    ADD CONSTRAINT fk_club_expenses_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_expenses fk_club_expenses_recurring_id_club_recurring_expenses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_expenses
    ADD CONSTRAINT fk_club_expenses_recurring_id_club_recurring_expenses FOREIGN KEY (recurring_id) REFERENCES public.club_recurring_expenses(id);


--
-- Name: club_external_coach_fees fk_club_external_coach_fees_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_external_coach_fees
    ADD CONSTRAINT fk_club_external_coach_fees_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_external_coach_fees fk_club_external_coach_fees_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_external_coach_fees
    ADD CONSTRAINT fk_club_external_coach_fees_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_external_coach_fees fk_club_external_coach_fees_expense_id_club_expenses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_external_coach_fees
    ADD CONSTRAINT fk_club_external_coach_fees_expense_id_club_expenses FOREIGN KEY (expense_id) REFERENCES public.club_expenses(id);


--
-- Name: club_external_coach_fees fk_club_external_coach_fees_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_external_coach_fees
    ADD CONSTRAINT fk_club_external_coach_fees_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_fees fk_club_fees_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_fees fk_club_fees_cash_received_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_cash_received_by_user_id_users FOREIGN KEY (cash_received_by_user_id) REFERENCES public.users(id);


--
-- Name: club_fees fk_club_fees_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_fees fk_club_fees_coach_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_coach_user_id_users FOREIGN KEY (coach_user_id) REFERENCES public.users(id);


--
-- Name: club_fees fk_club_fees_competition_id_club_competitions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_competition_id_club_competitions FOREIGN KEY (competition_id) REFERENCES public.club_competitions(id);


--
-- Name: club_fees fk_club_fees_course_id_club_courses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_course_id_club_courses FOREIGN KEY (course_id) REFERENCES public.club_courses(id);


--
-- Name: club_fees fk_club_fees_guardian_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_guardian_user_id_users FOREIGN KEY (guardian_user_id) REFERENCES public.users(id);


--
-- Name: club_fees fk_club_fees_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_fees fk_club_fees_paid_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_paid_by_user_id_users FOREIGN KEY (paid_by_user_id) REFERENCES public.users(id);


--
-- Name: club_fees fk_club_fees_paid_via_proof_id_club_payment_proofs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_paid_via_proof_id_club_payment_proofs FOREIGN KEY (paid_via_proof_id) REFERENCES public.club_payment_proofs(id);


--
-- Name: club_fees fk_club_fees_waived_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_fees
    ADD CONSTRAINT fk_club_fees_waived_by_user_id_users FOREIGN KEY (waived_by_user_id) REFERENCES public.users(id);


--
-- Name: club_functions fk_club_functions_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT fk_club_functions_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_functions fk_club_functions_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT fk_club_functions_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_functions fk_club_functions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT fk_club_functions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_functions fk_club_functions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_functions
    ADD CONSTRAINT fk_club_functions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_medical_certificates fk_club_medical_certificates_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_medical_certificates
    ADD CONSTRAINT fk_club_medical_certificates_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_medical_certificates fk_club_medical_certificates_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_medical_certificates
    ADD CONSTRAINT fk_club_medical_certificates_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_medical_certificates fk_club_medical_certificates_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_medical_certificates
    ADD CONSTRAINT fk_club_medical_certificates_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_medical_certificates fk_club_medical_certificates_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_medical_certificates
    ADD CONSTRAINT fk_club_medical_certificates_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_news_likes fk_club_news_likes_post_id_club_news_posts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_likes
    ADD CONSTRAINT fk_club_news_likes_post_id_club_news_posts FOREIGN KEY (post_id) REFERENCES public.club_news_posts(id) ON DELETE CASCADE;


--
-- Name: club_news_likes fk_club_news_likes_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_likes
    ADD CONSTRAINT fk_club_news_likes_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_news_posts fk_club_news_posts_author_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_posts
    ADD CONSTRAINT fk_club_news_posts_author_user_id_users FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: club_news_posts fk_club_news_posts_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_posts
    ADD CONSTRAINT fk_club_news_posts_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_news_posts fk_club_news_posts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_news_posts
    ADD CONSTRAINT fk_club_news_posts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_payment_proof_fees fk_club_payment_proof_fees_fee_id_club_fees; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proof_fees
    ADD CONSTRAINT fk_club_payment_proof_fees_fee_id_club_fees FOREIGN KEY (fee_id) REFERENCES public.club_fees(id);


--
-- Name: club_payment_proof_fees fk_club_payment_proof_fees_proof_id_club_payment_proofs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proof_fees
    ADD CONSTRAINT fk_club_payment_proof_fees_proof_id_club_payment_proofs FOREIGN KEY (proof_id) REFERENCES public.club_payment_proofs(id) ON DELETE CASCADE;


--
-- Name: club_payment_proofs fk_club_payment_proofs_cash_received_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proofs
    ADD CONSTRAINT fk_club_payment_proofs_cash_received_by_user_id_users FOREIGN KEY (cash_received_by_user_id) REFERENCES public.users(id);


--
-- Name: club_payment_proofs fk_club_payment_proofs_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proofs
    ADD CONSTRAINT fk_club_payment_proofs_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_payment_proofs fk_club_payment_proofs_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proofs
    ADD CONSTRAINT fk_club_payment_proofs_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_payment_proofs fk_club_payment_proofs_reviewed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proofs
    ADD CONSTRAINT fk_club_payment_proofs_reviewed_by_user_id_users FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id);


--
-- Name: club_payment_proofs fk_club_payment_proofs_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_payment_proofs
    ADD CONSTRAINT fk_club_payment_proofs_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_plans fk_club_plans_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_plans
    ADD CONSTRAINT fk_club_plans_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_plans fk_club_plans_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_plans
    ADD CONSTRAINT fk_club_plans_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_platform_fees fk_club_platform_fees_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_platform_fees
    ADD CONSTRAINT fk_club_platform_fees_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_platform_fees fk_club_platform_fees_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_platform_fees
    ADD CONSTRAINT fk_club_platform_fees_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_platform_fees fk_club_platform_fees_set_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_platform_fees
    ADD CONSTRAINT fk_club_platform_fees_set_by_user_id_users FOREIGN KEY (set_by_user_id) REFERENCES public.users(id);


--
-- Name: club_receipt_counters fk_club_receipt_counters_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_receipt_counters
    ADD CONSTRAINT fk_club_receipt_counters_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_recurring_expenses fk_club_recurring_expenses_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_recurring_expenses
    ADD CONSTRAINT fk_club_recurring_expenses_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_recurring_expenses fk_club_recurring_expenses_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_recurring_expenses
    ADD CONSTRAINT fk_club_recurring_expenses_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_recurring_expenses fk_club_recurring_expenses_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_recurring_expenses
    ADD CONSTRAINT fk_club_recurring_expenses_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_referees fk_club_referees_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT fk_club_referees_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id) ON DELETE CASCADE;


--
-- Name: club_referees fk_club_referees_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT fk_club_referees_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_referees fk_club_referees_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT fk_club_referees_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_referees fk_club_referees_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_referees
    ADD CONSTRAINT fk_club_referees_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_reminders_sent fk_club_reminders_sent_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reminders_sent
    ADD CONSTRAINT fk_club_reminders_sent_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_reports fk_club_reports_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reports
    ADD CONSTRAINT fk_club_reports_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_reports fk_club_reports_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reports
    ADD CONSTRAINT fk_club_reports_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: club_reports fk_club_reports_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_reports
    ADD CONSTRAINT fk_club_reports_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_school_letters fk_club_school_letters_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT fk_club_school_letters_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: club_school_letters fk_club_school_letters_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT fk_club_school_letters_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_school_letters fk_club_school_letters_competition_id_club_competitions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT fk_club_school_letters_competition_id_club_competitions FOREIGN KEY (competition_id) REFERENCES public.club_competitions(id);


--
-- Name: club_school_letters fk_club_school_letters_entry_id_club_competition_entries; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT fk_club_school_letters_entry_id_club_competition_entries FOREIGN KEY (entry_id) REFERENCES public.club_competition_entries(id);


--
-- Name: club_school_letters fk_club_school_letters_generated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT fk_club_school_letters_generated_by_user_id_users FOREIGN KEY (generated_by_user_id) REFERENCES public.users(id);


--
-- Name: club_school_letters fk_club_school_letters_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_school_letters
    ADD CONSTRAINT fk_club_school_letters_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_sites fk_club_sites_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_sites
    ADD CONSTRAINT fk_club_sites_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_sites fk_club_sites_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_sites
    ADD CONSTRAINT fk_club_sites_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_staff_messages fk_club_staff_messages_author_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_messages
    ADD CONSTRAINT fk_club_staff_messages_author_user_id_users FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: club_staff_messages fk_club_staff_messages_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_messages
    ADD CONSTRAINT fk_club_staff_messages_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_staff_messages fk_club_staff_messages_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_messages
    ADD CONSTRAINT fk_club_staff_messages_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_staff_messages fk_club_staff_messages_staff_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_messages
    ADD CONSTRAINT fk_club_staff_messages_staff_user_id_users FOREIGN KEY (staff_user_id) REFERENCES public.users(id);


--
-- Name: club_staff_rates fk_club_staff_rates_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_rates
    ADD CONSTRAINT fk_club_staff_rates_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_staff_rates fk_club_staff_rates_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_rates
    ADD CONSTRAINT fk_club_staff_rates_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_staff_rates fk_club_staff_rates_set_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_rates
    ADD CONSTRAINT fk_club_staff_rates_set_by_user_id_users FOREIGN KEY (set_by_user_id) REFERENCES public.users(id);


--
-- Name: club_staff_rates fk_club_staff_rates_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_rates
    ADD CONSTRAINT fk_club_staff_rates_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_staff_tasks fk_club_staff_tasks_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_tasks
    ADD CONSTRAINT fk_club_staff_tasks_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_staff_tasks fk_club_staff_tasks_expense_id_club_expenses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_tasks
    ADD CONSTRAINT fk_club_staff_tasks_expense_id_club_expenses FOREIGN KEY (expense_id) REFERENCES public.club_expenses(id) ON DELETE SET NULL;


--
-- Name: club_staff_tasks fk_club_staff_tasks_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_tasks
    ADD CONSTRAINT fk_club_staff_tasks_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_staff_tasks fk_club_staff_tasks_recorded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_tasks
    ADD CONSTRAINT fk_club_staff_tasks_recorded_by_user_id_users FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id);


--
-- Name: club_staff_tasks fk_club_staff_tasks_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_staff_tasks
    ADD CONSTRAINT fk_club_staff_tasks_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: club_transport_requests fk_club_transport_requests_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_transport_requests
    ADD CONSTRAINT fk_club_transport_requests_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_transport_requests fk_club_transport_requests_competition_id_club_competitions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_transport_requests
    ADD CONSTRAINT fk_club_transport_requests_competition_id_club_competitions FOREIGN KEY (competition_id) REFERENCES public.club_competitions(id);


--
-- Name: club_transport_requests fk_club_transport_requests_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_transport_requests
    ADD CONSTRAINT fk_club_transport_requests_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_transport_requests fk_club_transport_requests_sent_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_transport_requests
    ADD CONSTRAINT fk_club_transport_requests_sent_by_user_id_users FOREIGN KEY (sent_by_user_id) REFERENCES public.users(id);


--
-- Name: club_work_sessions fk_club_work_sessions_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_work_sessions
    ADD CONSTRAINT fk_club_work_sessions_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: club_work_sessions fk_club_work_sessions_corrected_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_work_sessions
    ADD CONSTRAINT fk_club_work_sessions_corrected_by_user_id_users FOREIGN KEY (corrected_by_user_id) REFERENCES public.users(id);


--
-- Name: club_work_sessions fk_club_work_sessions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_work_sessions
    ADD CONSTRAINT fk_club_work_sessions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: club_work_sessions fk_club_work_sessions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.club_work_sessions
    ADD CONSTRAINT fk_club_work_sessions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: clubs fk_clubs_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clubs
    ADD CONSTRAINT fk_clubs_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_adjustments fk_commission_adjustments_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: commission_adjustments fk_commission_adjustments_new_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_new_movement_id_commission_movements FOREIGN KEY (new_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_adjustments fk_commission_adjustments_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_adjustments fk_commission_adjustments_original_movement_id_commissi_4113; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_original_movement_id_commissi_4113 FOREIGN KEY (original_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_adjustments fk_commission_adjustments_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: commission_calculation_steps fk_commission_calculation_steps_beneficiary_agent_id_ag_5fea; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculation_steps
    ADD CONSTRAINT fk_commission_calculation_steps_beneficiary_agent_id_ag_5fea FOREIGN KEY (beneficiary_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: commission_calculation_steps fk_commission_calculation_steps_calculation_id_commissi_4b0f; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculation_steps
    ADD CONSTRAINT fk_commission_calculation_steps_calculation_id_commissi_4b0f FOREIGN KEY (calculation_id) REFERENCES public.commission_calculations(id);


--
-- Name: commission_calculations fk_commission_calculations_commission_plan_version_id_c_62c3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_commission_plan_version_id_c_62c3 FOREIGN KEY (commission_plan_version_id) REFERENCES public.commission_plan_versions(id);


--
-- Name: commission_calculations fk_commission_calculations_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: commission_calculations fk_commission_calculations_network_snapshot_id_network__9654; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_network_snapshot_id_network__9654 FOREIGN KEY (network_snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: commission_calculations fk_commission_calculations_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_movements fk_commission_movements_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: commission_movements fk_commission_movements_calculation_id_commission_calculations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_calculation_id_commission_calculations FOREIGN KEY (calculation_id) REFERENCES public.commission_calculations(id);


--
-- Name: commission_movements fk_commission_movements_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: commission_movements fk_commission_movements_network_snapshot_id_network_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_network_snapshot_id_network_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: commission_movements fk_commission_movements_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_offsets fk_commission_offsets_credit_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT fk_commission_offsets_credit_movement_id_commission_movements FOREIGN KEY (credit_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_offsets fk_commission_offsets_debit_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT fk_commission_offsets_debit_movement_id_commission_movements FOREIGN KEY (debit_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_offsets fk_commission_offsets_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT fk_commission_offsets_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_plan_versions fk_commission_plan_versions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_plan_versions
    ADD CONSTRAINT fk_commission_plan_versions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_reversals fk_commission_reversals_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: commission_reversals fk_commission_reversals_new_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_new_movement_id_commission_movements FOREIGN KEY (new_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_reversals fk_commission_reversals_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_reversals fk_commission_reversals_original_movement_id_commission_9fb0; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_original_movement_id_commission_9fb0 FOREIGN KEY (original_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_reversals fk_commission_reversals_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: commission_rule_versions fk_commission_rule_versions_commission_plan_version_id__cf5f; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_rule_versions
    ADD CONSTRAINT fk_commission_rule_versions_commission_plan_version_id__cf5f FOREIGN KEY (commission_plan_version_id) REFERENCES public.commission_plan_versions(id);


--
-- Name: companies fk_companies_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT fk_companies_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: contact_messages fk_contact_messages_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_messages
    ADD CONSTRAINT fk_contact_messages_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: contact_messages fk_contact_messages_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_messages
    ADD CONSTRAINT fk_contact_messages_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contract_attributions fk_contract_attributions_attributed_promoter_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT fk_contract_attributions_attributed_promoter_id_agent_profiles FOREIGN KEY (attributed_promoter_id) REFERENCES public.agent_profiles(id);


--
-- Name: contract_attributions fk_contract_attributions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT fk_contract_attributions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contract_attributions fk_contract_attributions_producer_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT fk_contract_attributions_producer_agent_id_agent_profiles FOREIGN KEY (producer_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: contract_commission_plans fk_contract_commission_plans_accepted_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_commission_plans
    ADD CONSTRAINT fk_contract_commission_plans_accepted_by_user_id_users FOREIGN KEY (accepted_by_user_id) REFERENCES public.users(id);


--
-- Name: contract_commission_plans fk_contract_commission_plans_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_commission_plans
    ADD CONSTRAINT fk_contract_commission_plans_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: contract_commission_plans fk_contract_commission_plans_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_commission_plans
    ADD CONSTRAINT fk_contract_commission_plans_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contract_events fk_contract_events_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_events
    ADD CONSTRAINT fk_contract_events_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: contract_instalments fk_contract_instalments_commission_calculation_id_commi_80b6; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_instalments
    ADD CONSTRAINT fk_contract_instalments_commission_calculation_id_commi_80b6 FOREIGN KEY (commission_calculation_id) REFERENCES public.commission_calculations(id);


--
-- Name: contract_instalments fk_contract_instalments_confirmed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_instalments
    ADD CONSTRAINT fk_contract_instalments_confirmed_by_user_id_users FOREIGN KEY (confirmed_by_user_id) REFERENCES public.users(id);


--
-- Name: contract_instalments fk_contract_instalments_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_instalments
    ADD CONSTRAINT fk_contract_instalments_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: contract_instalments fk_contract_instalments_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_instalments
    ADD CONSTRAINT fk_contract_instalments_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contract_requests fk_contract_requests_activated_by_promoter_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT fk_contract_requests_activated_by_promoter_id_agent_profiles FOREIGN KEY (activated_by_promoter_id) REFERENCES public.agent_profiles(id);


--
-- Name: contract_requests fk_contract_requests_bank_transfer_confirmed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT fk_contract_requests_bank_transfer_confirmed_by_user_id_users FOREIGN KEY (bank_transfer_confirmed_by_user_id) REFERENCES public.users(id);


--
-- Name: contract_requests fk_contract_requests_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT fk_contract_requests_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: contract_requests fk_contract_requests_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT fk_contract_requests_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: contract_requests fk_contract_requests_notes_updated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT fk_contract_requests_notes_updated_by_user_id_users FOREIGN KEY (notes_updated_by_user_id) REFERENCES public.users(id);


--
-- Name: contract_requests fk_contract_requests_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_requests
    ADD CONSTRAINT fk_contract_requests_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contract_status_history fk_contract_status_history_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_status_history
    ADD CONSTRAINT fk_contract_status_history_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: contract_status_history fk_contract_status_history_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_status_history
    ADD CONSTRAINT fk_contract_status_history_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: contracts fk_contracts_activated_by_promoter_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_activated_by_promoter_id_agent_profiles FOREIGN KEY (activated_by_promoter_id) REFERENCES public.agent_profiles(id);


--
-- Name: contracts fk_contracts_contract_attribution_id_contract_attributions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_contract_attribution_id_contract_attributions FOREIGN KEY (contract_attribution_id) REFERENCES public.contract_attributions(id);


--
-- Name: contracts fk_contracts_contract_request_id_contract_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_contract_request_id_contract_requests FOREIGN KEY (contract_request_id) REFERENCES public.contract_requests(id);


--
-- Name: contracts fk_contracts_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: contracts fk_contracts_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: contracts fk_contracts_first_referrer_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_first_referrer_agent_id_agent_profiles FOREIGN KEY (first_referrer_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: contracts fk_contracts_network_snapshot_id_network_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_network_snapshot_id_network_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: contracts fk_contracts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contracts fk_contracts_product_version_id_product_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_product_version_id_product_versions FOREIGN KEY (product_version_id) REFERENCES public.product_versions(id);


--
-- Name: contracts fk_contracts_terms_accepted_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_terms_accepted_by_user_id_users FOREIGN KEY (terms_accepted_by_user_id) REFERENCES public.users(id);


--
-- Name: customer_attributions fk_customer_attributions_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: customer_attributions fk_customer_attributions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: customer_attributions fk_customer_attributions_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_promoter_code_id_promoter_codes FOREIGN KEY (promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: customer_attributions fk_customer_attributions_referral_session_id_referral_sessions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_referral_session_id_referral_sessions FOREIGN KEY (referral_session_id) REFERENCES public.referral_sessions(id);


--
-- Name: customer_profiles fk_customer_profiles_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT fk_customer_profiles_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: customers fk_customers_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT fk_customers_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: customers fk_customers_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT fk_customers_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: documentation_posts fk_documentation_posts_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documentation_posts
    ADD CONSTRAINT fk_documentation_posts_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: documentation_posts fk_documentation_posts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documentation_posts
    ADD CONSTRAINT fk_documentation_posts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: documents fk_documents_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: documents fk_documents_contract_request_id_contract_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_contract_request_id_contract_requests FOREIGN KEY (contract_request_id) REFERENCES public.contract_requests(id);


--
-- Name: documents fk_documents_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: documents fk_documents_reviewed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_reviewed_by_user_id_users FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id);


--
-- Name: documents fk_documents_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: domain_outbox fk_domain_outbox_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_outbox
    ADD CONSTRAINT fk_domain_outbox_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: email_template_overrides fk_email_template_overrides_updated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_template_overrides
    ADD CONSTRAINT fk_email_template_overrides_updated_by_user_id_users FOREIGN KEY (updated_by_user_id) REFERENCES public.users(id);


--
-- Name: email_verification_tokens fk_email_verification_tokens_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT fk_email_verification_tokens_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: friend_referral_codes fk_friend_referral_codes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_codes
    ADD CONSTRAINT fk_friend_referral_codes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: friend_referral_codes fk_friend_referral_codes_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_codes
    ADD CONSTRAINT fk_friend_referral_codes_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: friend_referral_reward_claims fk_friend_referral_reward_claims_handled_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_reward_claims
    ADD CONSTRAINT fk_friend_referral_reward_claims_handled_by_user_id_users FOREIGN KEY (handled_by_user_id) REFERENCES public.users(id);


--
-- Name: friend_referral_reward_claims fk_friend_referral_reward_claims_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_reward_claims
    ADD CONSTRAINT fk_friend_referral_reward_claims_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: friend_referral_reward_claims fk_friend_referral_reward_claims_referrer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referral_reward_claims
    ADD CONSTRAINT fk_friend_referral_reward_claims_referrer_user_id_users FOREIGN KEY (referrer_user_id) REFERENCES public.users(id);


--
-- Name: friend_referrals fk_friend_referrals_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referrals
    ADD CONSTRAINT fk_friend_referrals_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: friend_referrals fk_friend_referrals_referred_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referrals
    ADD CONSTRAINT fk_friend_referrals_referred_customer_id_customers FOREIGN KEY (referred_customer_id) REFERENCES public.customers(id);


--
-- Name: friend_referrals fk_friend_referrals_referrer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friend_referrals
    ADD CONSTRAINT fk_friend_referrals_referrer_user_id_users FOREIGN KEY (referrer_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_order_items fk_jav_market_order_items_order_id_jav_market_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT fk_jav_market_order_items_order_id_jav_market_orders FOREIGN KEY (order_id) REFERENCES public.jav_market_orders(id) ON DELETE CASCADE;


--
-- Name: jav_market_order_items fk_jav_market_order_items_producer_id_jav_market_producers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT fk_jav_market_order_items_producer_id_jav_market_producers FOREIGN KEY (producer_id) REFERENCES public.jav_market_producers(id);


--
-- Name: jav_market_order_items fk_jav_market_order_items_product_id_jav_market_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT fk_jav_market_order_items_product_id_jav_market_products FOREIGN KEY (product_id) REFERENCES public.jav_market_products(id);


--
-- Name: jav_market_order_items fk_jav_market_order_items_supplier_dispatch_id_jav_mark_0ca7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT fk_jav_market_order_items_supplier_dispatch_id_jav_mark_0ca7 FOREIGN KEY (supplier_dispatch_id) REFERENCES public.jav_market_supplier_dispatches(id);


--
-- Name: jav_market_order_items fk_jav_market_order_items_variant_id_jav_market_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_order_items
    ADD CONSTRAINT fk_jav_market_order_items_variant_id_jav_market_variants FOREIGN KEY (variant_id) REFERENCES public.jav_market_variants(id);


--
-- Name: jav_market_orders fk_jav_market_orders_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_athlete_id_club_athletes FOREIGN KEY (athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: jav_market_orders fk_jav_market_orders_cancelled_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_cancelled_by_user_id_users FOREIGN KEY (cancelled_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_orders fk_jav_market_orders_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: jav_market_orders fk_jav_market_orders_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_orders fk_jav_market_orders_credit_debit_transaction_id_wallet_9f4f; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_credit_debit_transaction_id_wallet_9f4f FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.wallet_transactions(id);


--
-- Name: jav_market_orders fk_jav_market_orders_customer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_customer_user_id_users FOREIGN KEY (customer_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_orders fk_jav_market_orders_forwarded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_forwarded_by_user_id_users FOREIGN KEY (forwarded_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_orders fk_jav_market_orders_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: jav_market_orders fk_jav_market_orders_paid_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_orders
    ADD CONSTRAINT fk_jav_market_orders_paid_by_user_id_users FOREIGN KEY (paid_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_producers fk_jav_market_producers_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_producers
    ADD CONSTRAINT fk_jav_market_producers_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_producers fk_jav_market_producers_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_producers
    ADD CONSTRAINT fk_jav_market_producers_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: jav_market_products fk_jav_market_products_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_products
    ADD CONSTRAINT fk_jav_market_products_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: jav_market_products fk_jav_market_products_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_products
    ADD CONSTRAINT fk_jav_market_products_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_products fk_jav_market_products_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_products
    ADD CONSTRAINT fk_jav_market_products_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: jav_market_products fk_jav_market_products_producer_id_jav_market_producers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_products
    ADD CONSTRAINT fk_jav_market_products_producer_id_jav_market_producers FOREIGN KEY (producer_id) REFERENCES public.jav_market_producers(id);


--
-- Name: jav_market_settings fk_jav_market_settings_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_settings
    ADD CONSTRAINT fk_jav_market_settings_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: jav_market_supplier_dispatches fk_jav_market_supplier_dispatches_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_supplier_dispatches
    ADD CONSTRAINT fk_jav_market_supplier_dispatches_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: jav_market_supplier_dispatches fk_jav_market_supplier_dispatches_producer_id_jav_marke_4f29; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_supplier_dispatches
    ADD CONSTRAINT fk_jav_market_supplier_dispatches_producer_id_jav_marke_4f29 FOREIGN KEY (producer_id) REFERENCES public.jav_market_producers(id);


--
-- Name: jav_market_supplier_dispatches fk_jav_market_supplier_dispatches_sent_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_supplier_dispatches
    ADD CONSTRAINT fk_jav_market_supplier_dispatches_sent_by_user_id_users FOREIGN KEY (sent_by_user_id) REFERENCES public.users(id);


--
-- Name: jav_market_variants fk_jav_market_variants_product_id_jav_market_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jav_market_variants
    ADD CONSTRAINT fk_jav_market_variants_product_id_jav_market_products FOREIGN KEY (product_id) REFERENCES public.jav_market_products(id) ON DELETE CASCADE;


--
-- Name: javbot_conversations fk_javbot_conversations_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_conversations
    ADD CONSTRAINT fk_javbot_conversations_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: javbot_conversations fk_javbot_conversations_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_conversations
    ADD CONSTRAINT fk_javbot_conversations_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: javbot_conversations fk_javbot_conversations_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_conversations
    ADD CONSTRAINT fk_javbot_conversations_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: javbot_instructions fk_javbot_instructions_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_instructions
    ADD CONSTRAINT fk_javbot_instructions_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id) ON DELETE CASCADE;


--
-- Name: javbot_instructions fk_javbot_instructions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_instructions
    ADD CONSTRAINT fk_javbot_instructions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: javbot_instructions fk_javbot_instructions_updated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_instructions
    ADD CONSTRAINT fk_javbot_instructions_updated_by_user_id_users FOREIGN KEY (updated_by_user_id) REFERENCES public.users(id);


--
-- Name: javbot_knowledge_chunks fk_javbot_knowledge_chunks_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_chunks
    ADD CONSTRAINT fk_javbot_knowledge_chunks_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id) ON DELETE CASCADE;


--
-- Name: javbot_knowledge_chunks fk_javbot_knowledge_chunks_document_id_javbot_knowledge_2902; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_chunks
    ADD CONSTRAINT fk_javbot_knowledge_chunks_document_id_javbot_knowledge_2902 FOREIGN KEY (document_id) REFERENCES public.javbot_knowledge_documents(id) ON DELETE CASCADE;


--
-- Name: javbot_knowledge_chunks fk_javbot_knowledge_chunks_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_chunks
    ADD CONSTRAINT fk_javbot_knowledge_chunks_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: javbot_knowledge_documents fk_javbot_knowledge_documents_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_documents
    ADD CONSTRAINT fk_javbot_knowledge_documents_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: javbot_knowledge_documents fk_javbot_knowledge_documents_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_documents
    ADD CONSTRAINT fk_javbot_knowledge_documents_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: javbot_knowledge_documents fk_javbot_knowledge_documents_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_knowledge_documents
    ADD CONSTRAINT fk_javbot_knowledge_documents_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: javbot_messages fk_javbot_messages_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_messages
    ADD CONSTRAINT fk_javbot_messages_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: javbot_messages fk_javbot_messages_conversation_id_javbot_conversations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_messages
    ADD CONSTRAINT fk_javbot_messages_conversation_id_javbot_conversations FOREIGN KEY (conversation_id) REFERENCES public.javbot_conversations(id) ON DELETE CASCADE;


--
-- Name: javbot_messages fk_javbot_messages_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_messages
    ADD CONSTRAINT fk_javbot_messages_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: javbot_tasks fk_javbot_tasks_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_tasks
    ADD CONSTRAINT fk_javbot_tasks_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: javbot_tasks fk_javbot_tasks_conversation_id_javbot_conversations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_tasks
    ADD CONSTRAINT fk_javbot_tasks_conversation_id_javbot_conversations FOREIGN KEY (conversation_id) REFERENCES public.javbot_conversations(id) ON DELETE CASCADE;


--
-- Name: javbot_tasks fk_javbot_tasks_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_tasks
    ADD CONSTRAINT fk_javbot_tasks_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: javbot_tasks fk_javbot_tasks_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.javbot_tasks
    ADD CONSTRAINT fk_javbot_tasks_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: network_assignment_history fk_network_assignment_history_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_assignment_history fk_network_assignment_history_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: network_assignment_history fk_network_assignment_history_new_parent_agent_id_agent_149a; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_new_parent_agent_id_agent_149a FOREIGN KEY (new_parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_assignment_history fk_network_assignment_history_old_parent_agent_id_agent_6886; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_old_parent_agent_id_agent_6886 FOREIGN KEY (old_parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_assignment_history fk_network_assignment_history_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_assignment_history fk_network_assignment_history_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: network_closure fk_network_closure_ancestor_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT fk_network_closure_ancestor_agent_id_agent_profiles FOREIGN KEY (ancestor_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_closure fk_network_closure_descendant_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT fk_network_closure_descendant_agent_id_agent_profiles FOREIGN KEY (descendant_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_closure fk_network_closure_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT fk_network_closure_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_edges fk_network_edges_child_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT fk_network_edges_child_agent_id_agent_profiles FOREIGN KEY (child_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_edges fk_network_edges_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT fk_network_edges_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_edges fk_network_edges_parent_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT fk_network_edges_parent_agent_id_agent_profiles FOREIGN KEY (parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_nodes fk_network_nodes_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT fk_network_nodes_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_nodes fk_network_nodes_direct_parent_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT fk_network_nodes_direct_parent_agent_id_agent_profiles FOREIGN KEY (direct_parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_nodes fk_network_nodes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT fk_network_nodes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_snapshot_nodes fk_network_snapshot_nodes_ancestor_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT fk_network_snapshot_nodes_ancestor_agent_id_agent_profiles FOREIGN KEY (ancestor_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_snapshot_nodes fk_network_snapshot_nodes_rank_id_at_snapshot_ranks; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT fk_network_snapshot_nodes_rank_id_at_snapshot_ranks FOREIGN KEY (rank_id_at_snapshot) REFERENCES public.ranks(id);


--
-- Name: network_snapshot_nodes fk_network_snapshot_nodes_snapshot_id_network_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT fk_network_snapshot_nodes_snapshot_id_network_snapshots FOREIGN KEY (snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: network_snapshots fk_network_snapshots_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshots
    ADD CONSTRAINT fk_network_snapshots_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: notifications fk_notifications_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: notifications fk_notifications_recipient_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_recipient_user_id_users FOREIGN KEY (recipient_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_cancelled_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_cancelled_by_user_id_users FOREIGN KEY (cancelled_by_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_credit_debit_transaction_id_wallet_transactions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_credit_debit_transaction_id_wallet_transactions FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.wallet_transactions(id);


--
-- Name: orders fk_orders_customer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_customer_user_id_users FOREIGN KEY (customer_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: orders fk_orders_paid_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_paid_by_user_id_users FOREIGN KEY (paid_by_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_product_version_id_product_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_product_version_id_product_versions FOREIGN KEY (product_version_id) REFERENCES public.product_versions(id);


--
-- Name: otp_codes fk_otp_codes_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.otp_codes
    ADD CONSTRAINT fk_otp_codes_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: password_reset_tokens fk_password_reset_tokens_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT fk_password_reset_tokens_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: product_request_messages fk_product_request_messages_author_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_request_messages
    ADD CONSTRAINT fk_product_request_messages_author_user_id_users FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: product_request_messages fk_product_request_messages_request_id_product_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_request_messages
    ADD CONSTRAINT fk_product_request_messages_request_id_product_requests FOREIGN KEY (request_id) REFERENCES public.product_requests(id);


--
-- Name: product_requests fk_product_requests_opened_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_requests
    ADD CONSTRAINT fk_product_requests_opened_by_user_id_users FOREIGN KEY (opened_by_user_id) REFERENCES public.users(id);


--
-- Name: product_requests fk_product_requests_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_requests
    ADD CONSTRAINT fk_product_requests_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: product_versions fk_product_versions_commission_plan_version_id_commissi_c160; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_versions
    ADD CONSTRAINT fk_product_versions_commission_plan_version_id_commissi_c160 FOREIGN KEY (commission_plan_version_id) REFERENCES public.commission_plan_versions(id);


--
-- Name: product_versions fk_product_versions_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_versions
    ADD CONSTRAINT fk_product_versions_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: products fk_products_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT fk_products_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: promoter_codes fk_promoter_codes_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promoter_codes
    ADD CONSTRAINT fk_promoter_codes_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: promoter_codes fk_promoter_codes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promoter_codes
    ADD CONSTRAINT fk_promoter_codes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: ranks fk_ranks_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranks
    ADD CONSTRAINT fk_ranks_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: referral_events fk_referral_events_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_events
    ADD CONSTRAINT fk_referral_events_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: referral_events fk_referral_events_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_events
    ADD CONSTRAINT fk_referral_events_promoter_code_id_promoter_codes FOREIGN KEY (promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: referral_sessions fk_referral_sessions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_sessions
    ADD CONSTRAINT fk_referral_sessions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: referral_sessions fk_referral_sessions_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_sessions
    ADD CONSTRAINT fk_referral_sessions_promoter_code_id_promoter_codes FOREIGN KEY (promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: role_permissions fk_role_permissions_permission_id_permissions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT fk_role_permissions_permission_id_permissions FOREIGN KEY (permission_id) REFERENCES public.permissions(id);


--
-- Name: role_permissions fk_role_permissions_role_id_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT fk_role_permissions_role_id_roles FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: roles fk_roles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT fk_roles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: sessions fk_sessions_replaced_by_session_id_sessions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT fk_sessions_replaced_by_session_id_sessions FOREIGN KEY (replaced_by_session_id) REFERENCES public.sessions(id);


--
-- Name: sessions fk_sessions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT fk_sessions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: shop_categories fk_shop_categories_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_categories
    ADD CONSTRAINT fk_shop_categories_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: shop_categories fk_shop_categories_producer_id_jav_market_producers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_categories
    ADD CONSTRAINT fk_shop_categories_producer_id_jav_market_producers FOREIGN KEY (producer_id) REFERENCES public.jav_market_producers(id) ON DELETE SET NULL;


--
-- Name: shop_category_products fk_shop_category_products_category_id_shop_categories; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_category_products
    ADD CONSTRAINT fk_shop_category_products_category_id_shop_categories FOREIGN KEY (category_id) REFERENCES public.shop_categories(id) ON DELETE CASCADE;


--
-- Name: shop_category_products fk_shop_category_products_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shop_category_products
    ADD CONSTRAINT fk_shop_category_products_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: spend_pins fk_spend_pins_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spend_pins
    ADD CONSTRAINT fk_spend_pins_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: sponsors fk_sponsors_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sponsors
    ADD CONSTRAINT fk_sponsors_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: ticket_messages fk_ticket_messages_author_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT fk_ticket_messages_author_user_id_users FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: ticket_messages fk_ticket_messages_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT fk_ticket_messages_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);


--
-- Name: tickets fk_tickets_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: tickets fk_tickets_opened_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_opened_by_user_id_users FOREIGN KEY (opened_by_user_id) REFERENCES public.users(id);


--
-- Name: tickets fk_tickets_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_roles fk_user_roles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_roles fk_user_roles_role_id_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: user_roles fk_user_roles_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users fk_users_club_id_clubs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_club_id_clubs FOREIGN KEY (club_id) REFERENCES public.clubs(id);


--
-- Name: users fk_users_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: wallet_transactions fk_wallet_transactions_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: wallet_transactions fk_wallet_transactions_from_wallet_id_wallets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_from_wallet_id_wallets FOREIGN KEY (from_wallet_id) REFERENCES public.wallets(id);


--
-- Name: wallet_transactions fk_wallet_transactions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_club_athlete_id_club_athletes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_club_athlete_id_club_athletes FOREIGN KEY (reference_club_athlete_id) REFERENCES public.club_athletes(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_club_proof_id_club_pay_4409; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_club_proof_id_club_pay_4409 FOREIGN KEY (reference_club_proof_id) REFERENCES public.club_payment_proofs(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_contract_id_contracts FOREIGN KEY (reference_contract_id) REFERENCES public.contracts(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_jav_market_order_id_ja_9cb8; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_jav_market_order_id_ja_9cb8 FOREIGN KEY (reference_jav_market_order_id) REFERENCES public.jav_market_orders(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_order_id_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_order_id_orders FOREIGN KEY (reference_order_id) REFERENCES public.orders(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reverses_transaction_id_wallet_t_a759; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reverses_transaction_id_wallet_t_a759 FOREIGN KEY (reverses_transaction_id) REFERENCES public.wallet_transactions(id);


--
-- Name: wallet_transactions fk_wallet_transactions_to_wallet_id_wallets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_to_wallet_id_wallets FOREIGN KEY (to_wallet_id) REFERENCES public.wallets(id);


--
-- Name: wallets fk_wallets_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT fk_wallets_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: wallets fk_wallets_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT fk_wallets_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 0a0qXTYucsXCmZ9Yn5socFFxbrTK6v6hdcvq5ttcWofznu52iivvrfMqPhlHjp6

