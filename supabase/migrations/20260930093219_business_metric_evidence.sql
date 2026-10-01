CREATE TABLE public.business_metric_evidence (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company text NOT NULL,
    domain text NOT NULL,
    metric_name text NOT NULL,
    metric_label text NOT NULL,
    fiscal_year integer NOT NULL CHECK (fiscal_year BETWEEN 1900 AND 2100),
    metric_value numeric NOT NULL,
    unit text NOT NULL,
    scope text NOT NULL,
    source_document_id text NOT NULL,
    page_number integer NOT NULL CHECK (page_number > 0),
    source_quote text NOT NULL,
    source_url text NOT NULL,
    status text NOT NULL DEFAULT 'needs_review'
        CHECK (status IN ('needs_review', 'verified', 'rejected')),
    allowed_roles text[] NOT NULL DEFAULT '{}',
    entered_by text NOT NULL,
    verified_by text,
    verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company, metric_name, fiscal_year, source_document_id, page_number)
);

CREATE INDEX business_metric_evidence_dashboard_idx
    ON public.business_metric_evidence (company, domain, metric_name, fiscal_year)
    WHERE status = 'verified';
CREATE INDEX business_metric_evidence_review_idx
    ON public.business_metric_evidence (company, status, created_at DESC)
    WHERE status = 'needs_review';
CREATE UNIQUE INDEX business_metric_evidence_verified_period_uq
    ON public.business_metric_evidence (company, domain, metric_name, fiscal_year)
    WHERE status = 'verified';

ALTER TABLE public.business_metric_evidence ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.business_metric_evidence FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.business_metric_evidence TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.business_metric_evidence_id_seq TO service_role;

-- Public-report observations start pending. Admin review is required before dashboard use.
INSERT INTO public.business_metric_evidence (
    company, domain, metric_name, metric_label, fiscal_year, metric_value, unit,
    scope, source_document_id, page_number, source_quote, source_url, status, allowed_roles, entered_by
)
VALUES
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'farmer_raw_milk_purchased', 'Raw fresh milk purchased from farming households', 2023, 239254, 'tonnes', 'Group; farming households; annual purchased volume', 'VNM-SR-2023-EN', 67, '239,254 tons of raw fresh milk purchased in 2023', 'https://www.vinamilk.com.vn/phat-trien-ben-vung/bao-cao/2023/pdf/RGB-ENG-Vinamilk-SR-2023.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'total_raw_milk_supply', 'Total raw fresh milk supplied for production (approx.)', 2023, 408000, 'tonnes', 'Group; approximate annual production supply', 'VNM-AR-2023-EN', 103, 'The total volume of raw milk supplied for production reached 408,000 tons per year', 'https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2023/_astro/VINAMILK-ANNUAL-REPORT-2023.CA8i9BsJ.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'managed_farm_raw_milk', 'Raw milk produced by Vinamilk and Mộc Châu farms (approx.)', 2023, 168000, 'tonnes', 'Vinamilk managed farm system; approximate annual volume', 'VNM-AR-2023-EN', 103, 'Vinamilk’s farm system produces nearly 168,000 tons of raw milk per year', 'https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2023/_astro/VINAMILK-ANNUAL-REPORT-2023.CA8i9BsJ.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'farmer_raw_milk_purchased', 'Raw fresh milk contributed by household farmers (approx.)', 2024, 227000, 'tonnes', 'Group; household farmers; approximate annual volume', 'VNM-AR-2024-VI', 77, 'Household farmers contributed around 227,000 tons/year', 'https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/en/vinamilk-ar-eng-full-layout-interactive.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'total_raw_milk_supply', 'Total raw fresh milk supplied for production (approx.)', 2024, 408000, 'tonnes', 'Group; approximate annual volume; report p. 77 component rows total 408,000', 'VNM-AR-2024-VI', 77, 'Out of a total annual raw fresh milk production volume of 408,000 tons/year', 'https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/en/vinamilk-ar-eng-full-layout-interactive.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'total_raw_milk_supply', 'Raw milk supplied for production (conflicting report value)', 2024, 402000, 'tonnes', 'Group; management highlights; conflicts with annual report p. 77', 'VNM-AR-2024-VI', 60, 'Đảm bảo nguồn nguyên liệu đầu vào với đàn bò sữa đang quản lý đạt 130.000 con, cung cấp 402.000 tấn sữa cho sản xuất.', 'https://www.vinamilk.com.vn/bao-cao-thuong-nien/bao-cao/2024/doc/vi/full-bao-cao.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'farmer_raw_milk_purchased', 'Fresh milk purchased from farmers', 2025, 225778.211, 'tonnes', 'Group; farmer purchases; converted from 225,778,211 kg', 'VNM-SR-2025-EN', 112, '225,778,211 kg of milk purchased from farmers in 2025', 'https://d8um25gjecm9v.cloudfront.net/cms/VNMSR_EN_3ed5d9bc55.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research'),
('Công ty Cổ phần Sữa Việt Nam (Vinamilk)', 'milk_supply', 'total_raw_milk_supply', 'Total fresh milk supplied per year (approx.)', 2025, 410000, 'tonnes', 'Group; approximate annual supply', 'VNM-SR-2025-EN', 114, 'supplying approximately 410,000 tons of fresh milk per year', 'https://d8um25gjecm9v.cloudfront.net/cms/VNMSR_EN_3ed5d9bc55.pdf', 'needs_review', ARRAY['executive','sustainability_analyst','admin'], 'source_research')
ON CONFLICT (company, metric_name, fiscal_year, source_document_id, page_number) DO NOTHING;
