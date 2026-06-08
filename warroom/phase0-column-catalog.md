# Data Axle Phase 0 — Full Column Catalog (383 columns)

**Source files measured:** 16 combined CSVs in `data/data-axle/processed/`, totaling 17,042 dental-practice rows (Chicagoland + BOS metro, exports 2026-03-12 through 2026-03-14).

**Fill rate note:** Columns with fill_pct=100% but sentinel-zero values (e.g., `Affiliated Records` = always `"000000"`, `Corporate Employee Size Actual` = always `"000000"`) are noted. Sentinel-zero fill is NOT real data.

**Corporate-signal tiers:**
- **HIGH** — directly reveals common ownership across practices (shared officers, secondary EIN, parent/subsidiary linkage, back-office mailing, legal entity name, corporate-level financials distinct from location, franchise brand, location type)
- **MEDIUM** — weak / corroborating signal
- **NONE** — irrelevant for stealth-DSO detection (demographics, geo routing, SIC/NAICS noise, expense bands, social media, etc.)

---

| idx | Exact Header Name | Tier | Fill% (17k rows) | Example Value(s) | Reason |
|-----|-------------------|------|-----------------|------------------|--------|
| 0 | Company Name | MEDIUM | 100.0 | 25 East Dental; Aspen Dental | Trade name at location — stealth DSO will use retained local name here |
| 1 | Parent Company Name | HIGH | 1.5 | ADMI CORP; SONRAVA HEALTH; 1ST FAMILY DENTAL | Directly names corporate parent; low fill but 100% precision on DSO hits |
| 2 | Executive First Name | HIGH | 92.6 | Alan J; Kevin | Combined with Last Name across locations = shared-officer signal (exec #1 slot) |
| 3 | Executive Last Name | HIGH | 92.6 | Acierno; Landers | See above |
| 4 | Professional Title | NONE | 59.4 | DDS; DMD | Credential, not ownership signal |
| 5 | Executive Title | MEDIUM | 32.4 | Manager; President; Other | Role of exec #1 — "Manager" from DSO back-office, vs "President" for solo |
| 6 | Executive Gender | NONE | 86.6 | Male; Female | No ownership signal |
| 7 | Address | NONE | 99.3 | 105 W Madison St | Practice street address — already in NPPES |
| 8 | City | NONE | 100.0 | Chicago | Already in NPPES |
| 9 | State | NONE | 100.0 | IL | Already in NPPES |
| 10 | ZIP Code | NONE | 100.0 | 60602 | Already in NPPES |
| 11 | ZIP Four | NONE | 97.9 | 4602 | Routing code, no ownership signal |
| 12 | Carrier Route | NONE | 98.3 | C029 | USPS routing, no ownership signal |
| 13 | Delivery Point Barcode | NONE | 97.9 | 996 | USPS routing, no ownership signal |
| 14 | County | NONE | 100.0 | Cook | Geographic, no ownership signal |
| 15 | Metro Area | NONE | 100.0 | Chicago-Npvl, IL | Geographic, no ownership signal |
| 16 | Neighborhood | NONE | 45.8 | The Loop; Lockport | Geographic, no ownership signal |
| 17 | Phone Number Combined | NONE | 100.0 | (312) 442-0990 | Contact, already in NPPES |
| 18 | Fax Number Combined | NONE | 37.2 | 3122637013 | Contact only |
| 19 | Toll Free Number Combined | NONE | 3.7 | 8885069583 | Contact only; some DSOs have shared 1-800 |
| 20 | Website | MEDIUM | 54.8 | 25eastdental.Com | Website domain clustering can reveal DSO umbrella |
| 21 | Company Description | MEDIUM | 12.4 | "Aspen Dental Provides Comprehensive..." | Free-text may name parent brand |
| 22 | Primary SIC Code | NONE | 100.0 | 802101 | Industry classification, not ownership |
| 23 | Primary SIC Description | NONE | 100.0 | Dentists | Industry classification |
| 24 | Primary SIC Ad Size | NONE | 36.4 | Bold | Yellow-pages ad size, no ownership signal |
| 25 | Primary SIC Year Appeared | NONE | 100.0 | 2023 | Year in directory, not ownership |
| 26 | SIC Code 1 | NONE | 100.0 | 802101 | Duplicate of Primary SIC |
| 27 | SIC Code 1 Description | NONE | 100.0 | Dentists | Duplicate |
| 28 | SIC Code 1 Ad Size | NONE | 0.0 | — | Always empty |
| 29 | SIC Code 1 Year Appeared | NONE | 0.0 | — | Always empty |
| 30 | SIC Code 2 | NONE | 11.8 | 802104; 802101 | Secondary SIC, no ownership signal |
| 31 | SIC Code 2 Description | NONE | 11.8 | Cosmetic Dentistry | Secondary SIC description |
| 32 | SIC Code 2 Ad Size | NONE | 0.0 | — | Always empty |
| 33 | SIC Code 2 Year Appeared | NONE | 0.0 | — | Always empty |
| 34 | SIC Code 3 | NONE | 5.1 | 804914; 802106 | Tertiary SIC |
| 35 | SIC Code 3 Description | NONE | 5.1 | Dental Hygienists | Tertiary SIC |
| 36 | SIC Code 3 Ad Size | NONE | 0.0 | — | Always empty |
| 37 | SIC Code 3 Year Appeared | NONE | 0.0 | — | Always empty |
| 38 | SIC Code 4 | NONE | 2.4 | 866101; 807205 | Quaternary SIC |
| 39 | SIC Code 4 Description | NONE | 2.4 | Retreat Houses | Quaternary SIC |
| 40 | SIC Code 4 Ad Size | NONE | 0.0 | — | Always empty |
| 41 | SIC Code 4 Year Appeared | NONE | 0.0 | — | Always empty |
| 42 | SIC Code 5 | NONE | 1.0 | 807205 | Low-fill SIC noise |
| 43 | SIC Code 5 Description | NONE | 1.0 | Dental Implants-Prosthesis | Low-fill SIC noise |
| 44 | SIC Code 5 Ad Size | NONE | 0.0 | — | Always empty |
| 45 | SIC Code 5 Year Appeared | NONE | 0.0 | — | Always empty |
| 46 | SIC Code 6 | NONE | 0.3 | 874243; 862106 | Trace fill, noise |
| 47 | SIC Code 6 Description | NONE | 0.3 | Dental Practice-Management & Consultants | Trace fill |
| 48 | SIC Code 6 Ad Size | NONE | 0.0 | — | Always empty |
| 49 | SIC Code 6 Year Appeared | NONE | 0.0 | — | Always empty |
| 50 | SIC Code 7 | NONE | 0.1 | 999966 | Trace fill |
| 51 | SIC Code 7 Description | NONE | 0.1 | Federal Government Contractors | Trace fill |
| 52 | SIC Code 7 Ad Size | NONE | 0.0 | — | Always empty |
| 53 | SIC Code 7 Year Appeared | NONE | 0.0 | — | Always empty |
| 54 | SIC Code 8 | NONE | 0.1 | — | Trace fill |
| 55 | SIC Code 8 Description | NONE | 0.1 | — | Trace fill |
| 56 | SIC Code 8 Ad Size | NONE | 0.0 | — | Always empty |
| 57 | SIC Code 8 Year Appeared | NONE | 0.0 | — | Always empty |
| 58 | SIC Code 9 | NONE | 0.0 | — | Always empty |
| 59 | SIC Code 9 Description | NONE | 0.0 | — | Always empty |
| 60 | SIC Code 9 Ad Size | NONE | 0.0 | — | Always empty |
| 61 | SIC Code 9 Year Appeared | NONE | 0.0 | — | Always empty |
| 62 | SIC Code 10 | NONE | 0.0 | — | Always empty |
| 63 | SIC Code 10 Description | NONE | 0.0 | — | Always empty |
| 64 | SIC Code 10 Ad Size | NONE | 0.0 | — | Always empty |
| 65 | SIC Code 10 Year Appeared | NONE | 0.0 | — | Always empty |
| 66 | Primary NAICS | NONE | 100.0 | 62121003 | Industry, not ownership |
| 67 | Primary NAICS Description | NONE | 100.0 | Offices Of Dentists | Industry |
| 68 | NAICS 1 | NONE | 100.0 | 62121003 | Duplicate of Primary NAICS |
| 69 | NAICS 1 Description | NONE | 100.0 | Offices Of Dentists | Duplicate |
| 70 | NAICS 2 | NONE | 11.8 | 62121004 | Secondary NAICS, no ownership |
| 71 | NAICS 2 Description | NONE | 11.8 | Offices Of Dentists | Secondary NAICS |
| 72 | NAICS 3 | NONE | 5.1 | 62139955 | Tertiary NAICS |
| 73 | NAICS 3 Description | NONE | 5.1 | Offices Of All Other Misc Health Practitioners | Tertiary NAICS |
| 74 | NAICS 4 | NONE | 2.4 | 81311023 | Quaternary NAICS |
| 75 | NAICS 4 Description | NONE | 2.4 | Religious Organizations | Quaternary NAICS |
| 76 | NAICS 5 | NONE | 1.0 | 33911605 | Low-fill NAICS |
| 77 | NAICS 5 Description | NONE | 1.0 | Dental Laboratories | Low-fill NAICS |
| 78 | NAICS 6 | NONE | 0.3 | 54161111 | Trace fill |
| 79 | NAICS 6 Description | NONE | 0.3 | Administrative Management | Trace fill |
| 80 | NAICS 7 | NONE | 0.1 | 99999005 | Trace fill |
| 81 | NAICS 7 Description | NONE | 0.1 | Unclassified Establishments | Trace fill |
| 82 | NAICS 8 | NONE | 0.1 | — | Trace fill |
| 83 | NAICS 8 Description | NONE | 0.1 | — | Trace fill |
| 84 | NAICS 9 | NONE | 0.0 | — | Always empty |
| 85 | NAICS 9 Description | NONE | 0.0 | — | Always empty |
| 86 | NAICS 10 | NONE | 0.0 | — | Always empty |
| 87 | NAICS 10 Description | NONE | 0.0 | — | Always empty |
| 88 | Franchise Description 1 | HIGH | 68.5 | General Dentistry; Aspen Dental; Orthodontics | When value = brand name (not specialty), reveals DSO chain identity |
| 89 | Franchise Description 2 | MEDIUM | 1.2 | Oral Surgery; Orthodontics | Secondary specialty/franchise descriptor; very sparse |
| 90 | Franchise Description 3 | MEDIUM | 0.1 | Oral Surgery; Prosthodontics | Trace fill only |
| 91 | Franchise Description 4 | NONE | 0.1 | — | Effectively empty |
| 92 | Franchise Description 5 | NONE | 0.0 | — | Always empty |
| 93 | Cuisine Code | NONE | 0.0 | — | Always empty (restaurant field) |
| 94 | Cuisine Code Description | NONE | 0.0 | — | Always empty |
| 95 | Location Employee Size Range | MEDIUM | 99.8 | 5 to 9; 1 to 4 | Location headcount band; larger range may signal DSO |
| 96 | Location Employee Size Actual | MEDIUM | 100.0 | 00005; 00001 | Location headcount; higher values suggest corporate staffing |
| 97 | Location Sales Volume Range | MEDIUM | 98.7 | $500,000-1 Million; Less Than $500,000 | Revenue band; outliers may indicate DSO |
| 98 | Location Sales Volume Actual | MEDIUM | 100.0 | $633,000; $129,000 | Location revenue; already imported by importer |
| 99 | Corporate Employee Size Range | HIGH | 0.1* | 1000 to 4999 | When non-zero: confirms corporate parent; *sentinel "000000" for 99.9% |
| 100 | Corporate Employee Size Actual | HIGH | 0.1* | 001039 (ADMI Corp) | Total employees across corporate entity; sentinel "000000" = no data; only 14 real non-zero across 17k rows |
| 101 | Corporate Sales Volume Range | HIGH | 0.1* | $50-100 Million | When non-zero: reveals DSO-scale revenue; *sentinel zeros dominate |
| 102 | Corporate Sales Volume Actual | HIGH | 0.1* | $65,034,000 (ADMI); $0 | Corporate-level revenue distinct from location; sentinel "$0" dominates; only ~14 real values across 17k rows |
| 103 | Type of Business | MEDIUM | 100.0 | Private; Public | "Public" + dental = noteworthy (traded DSO) |
| 104 | Location Type | HIGH | 100.0 | Branch; Headquarter; Single Loc; Subsidiary | **Critical**: "Branch" (1.4%) and "Subsidiary" (0.1%) = corporate structure flag; "Headquarter" = DSO HQ |
| 105 | IUSA Number | HIGH | 100.0 | 78-379-2916 | Data Axle's internal unique record ID — links same entity across time snapshots |
| 106 | Parent IUSA Number | HIGH | 1.5* | 782271719 (ADMI/Aspen); 708712069 (1st Family) | Non-zero (1.5%) = direct parent linkage to corporate record; *sentinel "000000000" for rest |
| 107 | Subsidiary IUSA Number | HIGH | 0.8* | 638637645 (Aspen sub); 226552685 (Dentalworks sub) | Non-zero = points DOWN to subsidiary; *sentinel "000000000" for rest |
| 108 | Foreign Parent Flag | NONE | 0.0 | — | Always empty in dental dataset |
| 109 | EIN 1 | HIGH | 23.4 | 364160634; 271690957 | Primary tax ID — shared EIN across 3+ locations = definitive corporate linkage |
| 110 | EIN 2 | HIGH | 6.3 | 364327494; 043059901 | Second tax ID on record — same EIN appearing at another practice = strong corporate signal |
| 111 | EIN 3 | HIGH | 1.7 | 236191090; 464792826 | Third tax ID; low fill but precision on hits |
| 112 | Fortune 1000 Ranking | NONE | 100.0 | 0000 | All zeros in dental dataset; irrelevant |
| 113 | Credit Cards Accepted | NONE | 36.5 | ADMV; MV | Payment codes, no ownership signal |
| 114 | Last Updated On | NONE | 100.0 | 202409; 202602 | Record freshness date, not ownership |
| 115 | Years In Database | NONE | 100.0 | 4; 8 | Database tenure, not ownership |
| 116 | Year Established | MEDIUM | 9.7 | 1942; 2017 | Vintage; recent + corporate signals may indicate acquisition |
| 117 | Square Footage | NONE | 39.2 | 1,500-2,499; 2,500-4,999 | Physical size, not ownership |
| 118 | Home Business | NONE | 100.0 | No | Always "No" in dental dataset |
| 119 | Credit Score Alpha | NONE | 100.0 | A; B+ | Credit rating, not ownership |
| 120 | Latitude | NONE | 100.0 | 041.881806 | Geo coord, not ownership |
| 121 | Longitude | NONE | 100.0 | -087.631242 | Geo coord |
| 122 | Government Office | NONE | 100.0 | 0; 1 | Government flag; 1 = VA/clinic system |
| 123 | Location Centerpoint | NONE | 100.0 | Parcel; Site Level | Geocode precision, not ownership |
| 124 | Import Export Flag | NONE | 0.0 | — | Always empty |
| 125 | Own or Lease | MEDIUM | 100.0 | Unknown; Own; Lease | "Lease" common for DSO branch; "Own" more solo |
| 126 | Firm or Individual | HIGH | 100.0 | 2 (Firm); 1 (Individual) | "2"=Firm/corporate entity; "1"=individual provider; already imported |
| 127 | Monday Open | NONE | 32.8 | 0800 | Hours, not ownership |
| 128 | Monday Close | NONE | 30.7 | 1700 | Hours |
| 129 | Tuesday Open | NONE | 32.8 | 0800 | Hours |
| 130 | Tuesday Close | NONE | 30.9 | 1700 | Hours |
| 131 | Wednesday Open | NONE | 32.8 | 0800 | Hours |
| 132 | Wednesday Close | NONE | 28.0 | 1700 | Hours |
| 133 | Thursday Open | NONE | 32.8 | 0800 | Hours |
| 134 | Thursday Close | NONE | 30.3 | 1700 | Hours |
| 135 | Friday Open | NONE | 32.8 | 0800 | Hours |
| 136 | Friday Close | NONE | 24.2 | 1400 | Hours |
| 137 | Saturday Open | NONE | 32.8 | Closed; 0900 | Extended weekend hours may suggest DSO staffing |
| 138 | Saturday Close | NONE | 17.6 | 1500 | Hours |
| 139 | Sunday Open | NONE | 32.8 | Closed; 1200 | Hours |
| 140 | Sunday Close | NONE | 1.0 | 1400 | Hours |
| 141 | Executive First Name 1 | HIGH | 92.6 | Alan J; Kevin | Duplicate of col 2 — same person, same signal |
| 142 | Executive Last Name 1 | HIGH | 92.6 | Acierno; Landers | Duplicate of col 3 |
| 143 | Executive Title 1 | MEDIUM | 32.4 | Manager; President; Other | Role context for exec #1 |
| 144 | Executive Gender 1 | NONE | 86.6 | Male; Female | No ownership signal |
| 145 | Executive First Name 2 | HIGH | 13.5 | Alyson; Ken | Second officer — cross-practice officer overlap = corporate cluster |
| 146 | Executive Last Name 2 | HIGH | 13.5 | Koslow; Cae | Second officer last name |
| 147 | Executive Title 2 | MEDIUM | 13.5 | Operations; Exec Director | Role context; "Operations" = back-office DSO role |
| 148 | Executive Gender 2 | NONE | 12.0 | Female; Male | No ownership signal |
| 149 | Executive First Name 3 | HIGH | 6.3 | Kim; Samia | Third officer |
| 150 | Executive Last Name 3 | HIGH | 6.3 | Fitzsimmons; Akhras | Third officer |
| 151 | Executive Title 3 | MEDIUM | 6.3 | Director; Office Manager | Role context |
| 152 | Executive Gender 3 | NONE | 5.5 | Female | No ownership signal |
| 153 | Executive First Name 4 | HIGH | 2.9 | Allison; Laila | Fourth officer — multi-officer presence alone signals larger org |
| 154 | Executive Last Name 4 | HIGH | 2.9 | Houle; Dakak | Fourth officer |
| 155 | Executive Title 4 | MEDIUM | 2.9 | Manager; Office Manager | Role context |
| 156 | Executive Gender 4 | NONE | 2.5 | Female | No ownership signal |
| 157 | Executive First Name 5 | HIGH | 1.6 | Justine; Alexis | Fifth officer |
| 158 | Executive Last Name 5 | HIGH | 1.6 | Radies; Turnage | Fifth officer |
| 159 | Executive Title 5 | MEDIUM | 1.6 | Manager; Operations | Role context |
| 160 | Executive Gender 5 | NONE | 1.3 | Female | No ownership signal |
| 161 | Executive First Name 6 | HIGH | 1.0 | Nicole; Ariana | Sixth officer |
| 162 | Executive Last Name 6 | HIGH | 1.0 | Rousseaux; Garcia | Sixth officer |
| 163 | Executive Title 6 | MEDIUM | 1.0 | Manager; Director | Role context |
| 164 | Executive Gender 6 | NONE | 0.8 | Female | No ownership signal |
| 165 | Executive First Name 7 | HIGH | 0.7 | Paul; Joseph | Seventh officer |
| 166 | Executive Last Name 7 | HIGH | 0.7 | Young; Blackwell | Seventh officer |
| 167 | Executive Title 7 | MEDIUM | 0.7 | Manager; Regional Mgr | Role context |
| 168 | Executive Gender 7 | NONE | 0.6 | Male | No ownership signal |
| 169 | Executive First Name 8 | HIGH | 0.5 | Ken; Marie | Eighth officer |
| 170 | Executive Last Name 8 | HIGH | 0.5 | Widelka; Wetendorf | Eighth officer |
| 171 | Executive Title 8 | MEDIUM | 0.5 | COO; Office Manager | "COO" at a dental practice = corporate structure signal |
| 172 | Executive Gender 8 | NONE | 0.4 | Male; Female | No ownership signal |
| 173 | Executive First Name 9 | HIGH | 0.4 | Rebecca; Mike | Ninth officer |
| 174 | Executive Last Name 9 | HIGH | 0.4 | Perry; Mcdermott | Ninth officer |
| 175 | Executive Title 9 | MEDIUM | 0.4 | CFO; CFO | "CFO" at a dental practice = definitive corporate signal |
| 176 | Executive Gender 9 | NONE | 0.4 | Female; Male | No ownership signal |
| 177 | Executive First Name 10 | HIGH | 0.3 | Jay; Michael | Tenth officer |
| 178 | Executive Last Name 10 | HIGH | 0.3 | Rosenblum; Bentley | Tenth officer |
| 179 | Executive Title 10 | MEDIUM | 0.3 | Sales Exec; Operations | Role context |
| 180 | Executive Gender 10 | NONE | 0.2 | Male | No ownership signal |
| 181 | Executive First Name 11 | HIGH | 0.3 | Jay; Scott B | Eleventh officer |
| 182 | Executive Last Name 11 | HIGH | 0.3 | Rosenblum; Kalniz | Eleventh officer |
| 183 | Executive Title 11 | MEDIUM | 0.3 | Finance Exec; Board Member | "Board Member" = corporate governance signal |
| 184 | Executive Gender 11 | NONE | 0.2 | Male | No ownership signal |
| 185 | Executive First Name 12 | HIGH | 0.2 | Dave; Jonathan | Twelfth officer |
| 186 | Executive Last Name 12 | HIGH | 0.2 | Siegler; Shenkin | Twelfth officer |
| 187 | Executive Title 12 | MEDIUM | 0.2 | IT Executive; Vice President | Role context |
| 188 | Executive Gender 12 | NONE | 0.1 | Male | No ownership signal |
| 189 | Executive First Name 13 | HIGH | 0.2 | Alma; Raymond | Thirteenth officer |
| 190 | Executive Last Name 13 | HIGH | 0.2 | Hundiak; Cohlmia | Thirteenth officer |
| 191 | Executive Title 13 | MEDIUM | 0.2 | IT; Exec Director | Role context |
| 192 | Executive Gender 13 | NONE | 0.2 | Female | No ownership signal |
| 193 | Executive First Name 14 | HIGH | 0.2 | Beverly; Kathleen | Fourteenth officer |
| 194 | Executive Last Name 14 | HIGH | 0.2 | Albert; Oloughlin | Fourteenth officer |
| 195 | Executive Title 14 | MEDIUM | 0.2 | Other; Exec Director | Role context |
| 196 | Executive Gender 14 | NONE | 0.2 | Female | No ownership signal |
| 197 | Executive First Name 15 | HIGH | 0.2 | Karen; Berry | Fifteenth officer |
| 198 | Executive Last Name 15 | HIGH | 0.2 | Allison; James | Fifteenth officer |
| 199 | Executive Title 15 | MEDIUM | 0.2 | Other; Publisher/Editor | Role context |
| 200 | Executive Gender 15 | NONE | 0.2 | Female | No ownership signal |
| 201 | Executive First Name 16 | HIGH | 0.2 | Trina R; Ben | Sixteenth officer |
| 202 | Executive Last Name 16 | HIGH | 0.2 | Andresen; Maizell | Sixteenth officer |
| 203 | Executive Title 16 | MEDIUM | 0.2 | Other; Publisher/Editor | Role context |
| 204 | Executive Gender 16 | NONE | 0.2 | Female | No ownership signal |
| 205 | Executive First Name 17 | HIGH | 0.2 | Ivana; Ann | Seventeenth officer |
| 206 | Executive Last Name 17 | HIGH | 0.2 | Bevacqua; Battrell | Seventeenth officer |
| 207 | Executive Title 17 | MEDIUM | 0.2 | Other; Director | Role context |
| 208 | Executive Gender 17 | NONE | 0.2 | Female | No ownership signal |
| 209 | Executive First Name 18 | HIGH | 0.2 | Harriet M; Mary | Eighteenth officer |
| 210 | Executive Last Name 18 | HIGH | 0.2 | Bogdanowicz; Borysewicz | Eighteenth officer |
| 211 | Executive Title 18 | MEDIUM | 0.2 | Other; Director | Role context |
| 212 | Executive Gender 18 | NONE | 0.1 | Female | No ownership signal |
| 213 | Executive First Name 19 | HIGH | 0.2 | Jill E; Peter | Nineteenth officer |
| 214 | Executive Last Name 19 | HIGH | 0.2 | Forister; Bradley | Nineteenth officer |
| 215 | Executive Title 19 | MEDIUM | 0.2 | Other; Director | Role context |
| 216 | Executive Gender 19 | NONE | 0.2 | Male | No ownership signal |
| 217 | Executive First Name 20 | HIGH | 0.2 | Jennifer; Nicole | Twentieth officer |
| 218 | Executive Last Name 20 | HIGH | 0.2 | Gibson; Cramlett | Twentieth officer |
| 219 | Executive Title 20 | MEDIUM | 0.2 | Other; Director | Role context |
| 220 | Executive Gender 20 | NONE | 0.1 | Female | No ownership signal |
| 221 | Executive First Name 21 | HIGH | 0.1 | Alyson; Stacie | 21st officer |
| 222 | Executive Last Name 21 | HIGH | 0.1 | Hall; Crozier | 21st officer |
| 223 | Executive Title 21 | MEDIUM | 0.1 | Other; Director | Role context |
| 224 | Executive Gender 21 | NONE | 0.1 | Female | No ownership signal |
| 225 | Executive First Name 22 | HIGH | 0.1 | Helen; Heidi | 22nd officer |
| 226 | Executive Last Name 22 | HIGH | 0.1 | Jameson; Duggan | 22nd officer |
| 227 | Executive Title 22 | MEDIUM | 0.1 | Other; Director | Role context |
| 228 | Executive Gender 22 | NONE | 0.1 | Female | No ownership signal |
| 229 | Executive First Name 23 | HIGH | 0.1 | Debby; Sandra | 23rd officer |
| 230 | Executive Last Name 23 | HIGH | 0.1 | Rice; Eitel | 23rd officer |
| 231 | Executive Title 23 | MEDIUM | 0.1 | Other; Director | Role context |
| 232 | Executive Gender 23 | NONE | 0.1 | Female | No ownership signal |
| 233 | Executive First Name 24 | HIGH | 0.1 | Jill; Tony | 24th officer |
| 234 | Executive Last Name 24 | HIGH | 0.1 | Sahagian; Frankos | 24th officer |
| 235 | Executive Title 24 | MEDIUM | 0.1 | Other; Director | Role context |
| 236 | Executive Gender 24 | NONE | 0.1 | Female | No ownership signal |
| 237 | Executive First Name 25 | HIGH | 0.1 | Brenda; William | 25th officer |
| 238 | Executive Last Name 25 | HIGH | 0.1 | Stewart; Gilroy | 25th officer |
| 239 | Executive Title 25 | MEDIUM | 0.1 | Other; Director | Role context |
| 240 | Executive Gender 25 | NONE | 0.1 | Female | No ownership signal |
| 241 | Executive First Name 26 | HIGH | 0.1 | Jane | 26th officer |
| 242 | Executive Last Name 26 | HIGH | 0.1 | Grover | 26th officer |
| 243 | Executive Title 26 | MEDIUM | 0.1 | Director | Role context |
| 244 | Executive Gender 26 | NONE | 0.1 | Female | No ownership signal |
| 245 | Executive First Name 27 | HIGH | 0.1 | Barbra | 27th officer |
| 246 | Executive Last Name 27 | HIGH | 0.1 | Josephson | 27th officer |
| 247 | Executive Title 27 | MEDIUM | 0.1 | Director | Role context |
| 248 | Executive Gender 27 | NONE | 0.1 | Female | No ownership signal |
| 249 | Executive First Name 28 | HIGH | 0.1 | Kenny | 28th officer |
| 250 | Executive Last Name 28 | HIGH | 0.1 | Kaplan | 28th officer |
| 251 | Executive Title 28 | MEDIUM | 0.1 | Director | Role context |
| 252 | Executive Gender 28 | NONE | 0.1 | Male | No ownership signal |
| 253 | Executive First Name 29 | HIGH | 0.1 | H | 29th officer |
| 254 | Executive Last Name 29 | HIGH | 0.1 | Karen | 29th officer |
| 255 | Executive Title 29 | MEDIUM | 0.1 | Director | Role context |
| 256 | Executive Gender 29 | NONE | 0.0 | — | Effectively empty |
| 257 | Executive First Name 30 | HIGH | 0.1 | Michelle | 30th officer |
| 258 | Executive Last Name 30 | HIGH | 0.1 | Kruse | 30th officer |
| 259 | Executive Title 30 | MEDIUM | 0.1 | Director | Role context |
| 260 | Executive Gender 30 | NONE | 0.1 | Female | No ownership signal |
| 261 | Executive First Name 31 | HIGH | 0.1 | Tera | 31st officer |
| 262 | Executive Last Name 31 | HIGH | 0.1 | Lavick | 31st officer |
| 263 | Executive Title 31 | MEDIUM | 0.1 | Director | Role context |
| 264 | Executive Gender 31 | NONE | 0.1 | Female | No ownership signal |
| 265 | Executive First Name 32 | HIGH | 0.1 | Sandy | 32nd officer |
| 266 | Executive Last Name 32 | HIGH | 0.1 | Lieberman | 32nd officer |
| 267 | Executive Title 32 | MEDIUM | 0.1 | Director | Role context |
| 268 | Executive Gender 32 | NONE | 0.1 | Female | No ownership signal |
| 269 | Executive First Name 33 | HIGH | 0.1 | Chris | 33rd officer |
| 270 | Executive Last Name 33 | HIGH | 0.1 | Maag | 33rd officer |
| 271 | Executive Title 33 | MEDIUM | 0.1 | Director | Role context |
| 272 | Executive Gender 33 | NONE | 0.1 | Male | No ownership signal |
| 273 | Executive First Name 34 | HIGH | 0.1 | Janine | 34th officer |
| 274 | Executive Last Name 34 | HIGH | 0.1 | Maclachlan | 34th officer |
| 275 | Executive Title 34 | MEDIUM | 0.1 | Director | Role context |
| 276 | Executive Gender 34 | NONE | 0.0 | — | Effectively empty |
| 277 | Executive First Name 35 | HIGH | 0.1 | Dawn | 35th officer |
| 278 | Executive Last Name 35 | HIGH | 0.1 | Mcevoy | 35th officer |
| 279 | Executive Title 35 | MEDIUM | 0.1 | Director | Role context |
| 280 | Executive Gender 35 | NONE | 0.1 | Female | No ownership signal |
| 281 | Executive First Name 36 | HIGH | 0.1 | Spiro | 36th officer |
| 282 | Executive Last Name 36 | HIGH | 0.1 | Megremis | 36th officer |
| 283 | Executive Title 36 | MEDIUM | 0.1 | Director | Role context |
| 284 | Executive Gender 36 | NONE | 0.1 | Male | No ownership signal |
| 285 | Executive First Name 37 | HIGH | 0.1 | Catherine | 37th officer |
| 286 | Executive Last Name 37 | HIGH | 0.1 | Mills | 37th officer |
| 287 | Executive Title 37 | MEDIUM | 0.1 | Director | Role context |
| 288 | Executive Gender 37 | NONE | 0.0 | — | Effectively empty |
| 289 | Executive First Name 38 | HIGH | 0.1 | Chris | 38th officer |
| 290 | Executive Last Name 38 | HIGH | 0.1 | Mitchell | 38th officer |
| 291 | Executive Title 38 | MEDIUM | 0.1 | Director | Role context |
| 292 | Executive Gender 38 | NONE | 0.1 | Male | No ownership signal |
| 293 | Executive First Name 39 | HIGH | 0.1 | Jean | 39th officer |
| 294 | Executive Last Name 39 | HIGH | 0.1 | Narcisi | 39th officer |
| 295 | Executive Title 39 | MEDIUM | 0.1 | Director | Role context |
| 296 | Executive Gender 39 | NONE | 0.0 | — | Effectively empty |
| 297 | Executive First Name 40 | HIGH | 0.1 | Chad | 40th officer |
| 298 | Executive Last Name 40 | HIGH | 0.1 | Olson | 40th officer |
| 299 | Executive Title 40 | MEDIUM | 0.1 | Director | Role context |
| 300 | Executive Gender 40 | NONE | 0.0 | — | Effectively empty |
| 301 | Executive First Name 41 | HIGH | 0.1 | Robert | 41st officer |
| 302 | Executive Last Name 41 | HIGH | 0.1 | Quashie | 41st officer |
| 303 | Executive Title 41 | MEDIUM | 0.1 | Director | Role context |
| 304 | Executive Gender 41 | NONE | 0.1 | Male | No ownership signal |
| 305 | Executive First Name 42 | HIGH | 0.1 | Mazhar | 42nd officer |
| 306 | Executive Last Name 42 | HIGH | 0.1 | Said | 42nd officer |
| 307 | Executive Title 42 | MEDIUM | 0.1 | Director | Role context |
| 308 | Executive Gender 42 | NONE | 0.0 | — | Effectively empty |
| 309 | Executive First Name 43 | NONE | 0.0 | — | Always empty in this dataset |
| 310 | Executive Last Name 43 | NONE | 0.0 | — | Always empty |
| 311 | Executive Title 43 | NONE | 0.0 | — | Always empty |
| 312 | Executive Gender 43 | NONE | 0.0 | — | Always empty |
| 313 | Executive First Name 44 | NONE | 0.0 | — | Always empty |
| 314 | Executive Last Name 44 | NONE | 0.0 | — | Always empty |
| 315 | Executive Title 44 | NONE | 0.0 | — | Always empty |
| 316 | Executive Gender 44 | NONE | 0.0 | — | Always empty |
| 317 | Executive First Name 45 | NONE | 0.0 | — | Always empty |
| 318 | Executive Last Name 45 | NONE | 0.0 | — | Always empty |
| 319 | Executive Title 45 | NONE | 0.0 | — | Always empty |
| 320 | Executive Gender 45 | NONE | 0.0 | — | Always empty |
| 321 | Executive First Name 46 | NONE | 0.0 | — | Always empty |
| 322 | Executive Last Name 46 | NONE | 0.0 | — | Always empty |
| 323 | Executive Title 46 | NONE | 0.0 | — | Always empty |
| 324 | Executive Gender 46 | NONE | 0.0 | — | Always empty |
| 325 | Executive First Name 47 | NONE | 0.0 | — | Always empty |
| 326 | Executive Last Name 47 | NONE | 0.0 | — | Always empty |
| 327 | Executive Title 47 | NONE | 0.0 | — | Always empty |
| 328 | Executive Gender 47 | NONE | 0.0 | — | Always empty |
| 329 | Executive First Name 48 | NONE | 0.0 | — | Always empty |
| 330 | Executive Last Name 48 | NONE | 0.0 | — | Always empty |
| 331 | Executive Title 48 | NONE | 0.0 | — | Always empty |
| 332 | Executive Gender 48 | NONE | 0.0 | — | Always empty |
| 333 | Executive First Name 49 | NONE | 0.0 | — | Always empty |
| 334 | Executive Last Name 49 | NONE | 0.0 | — | Always empty |
| 335 | Executive Title 49 | NONE | 0.0 | — | Always empty |
| 336 | Executive Gender 49 | NONE | 0.0 | — | Always empty |
| 337 | Executive First Name 50 | NONE | 0.0 | — | Always empty |
| 338 | Executive Last Name 50 | NONE | 0.0 | — | Always empty |
| 339 | Executive Title 50 | NONE | 0.0 | — | Always empty |
| 340 | Executive Gender 50 | NONE | 0.0 | — | Always empty |
| 341 | Ticker Symbol | NONE | 0.0 | — | Always empty; dental practices rarely public |
| 342 | Stock Exchange | NONE | 0.0 | — | Always empty |
| 343 | Accounting Expenses | NONE | 27.2 | $2,500 to $5,000 | Expense bands, not ownership signal |
| 344 | Advertising  Expenses | NONE | 27.4 | $10,000 to $20,000 | Note: double-space in header ("Advertising  Expenses"); expense band |
| 345 | Computer Expenses | NONE | 27.4 | $2,500 to $5,000 | Expense band |
| 346 | Contract Labor Expenses | NONE | 27.4 | $1,000 to $10,000 | Expense band |
| 347 | Insurance Expenses | NONE | 26.9 | $5,000 to $10,000 | Expense band |
| 348 | Legal Expenses | NONE | 27.2 | $1,000 to $2,500 | Expense band |
| 349 | Office Supplies Expense | NONE | 27.0 | $10,000 to $20,000 | Expense band |
| 350 | Management/Administration Expenses | NONE | 27.4 | $10,000 to $25,000 | Expense band |
| 351 | Package Container Expense | NONE | 26.8 | Less than $500 | Expense band |
| 352 | Payroll and Benefits Expenses | NONE | 27.4 | $250,000 to $500,000 | Expense band |
| 353 | Purchase Print Expenses | NONE | 26.9 | $1,000 to $2,500 | Expense band |
| 354 | Rent Expenses | NONE | 27.4 | $25,000 to $50,000 | Expense band |
| 355 | Telcom Expenses | NONE | 27.4 | $2,000 to $5,000 | Expense band |
| 356 | Utilities Expenses | NONE | 27.4 | $5,000 to $10,000 | Expense band |
| 357 | Mailing Address | HIGH | 5.4 | 5001 Prospect Ave #3b; PO Box 11568 | When different from practice address = back-office/corporate mailing |
| 358 | Mailing City | HIGH | 25.9 | Chicago; Fort Worth; Zionsville (IN) | Out-of-state mailing city = corporate HQ signal |
| 359 | Mailing State | HIGH | 25.9 | IL; TX; KY | Out-of-state mailing = corporate parent in different state |
| 360 | Mailing Zip Code | HIGH | 25.9 | 60602; 10010 | Shared mailing ZIP across multiple practices = back-office cluster |
| 361 | Mailing Zip Four | MEDIUM | 5.2 | 3790; 4218 | More precise mailing address when present |
| 362 | Mailing Carrier Route | NONE | 5.3 | C014 | USPS routing, redundant with ZIP |
| 363 | Mailing Delivery Point Bar Code | NONE | 5.3 | 996 | USPS routing, redundant |
| 364 | Twitter | NONE | 9.6 | https://twitter.com/25eastdental | Social media, not ownership |
| 365 | Linked-In | MEDIUM | 2.1 | https://linkedin.com/company/elite-dental-partners | Company LinkedIn may reveal parent entity |
| 366 | Facebook | NONE | 24.0 | https://www.facebook.com/25eastdental/ | Social media, not ownership |
| 367 | Franchise/Specialty Code 2.0 | MEDIUM | 5.6 | Orthodontics; Periodontics; Endodontics | Secondary specialty; "Orthodontics" at a GP = specialty DSO overlap |
| 368 | Franchise/Specialty Code 2.1 | NONE | 0.2 | Pedodontics | Trace fill, sub-code |
| 369 | Franchise/Specialty Code 3.0 | MEDIUM | 1.6 | Prosthodontics; Oral Surgery; Pedodontics | Tertiary specialty |
| 370 | Franchise/Specialty Code 3.1 | NONE | 0.1 | — | Trace fill |
| 371 | Franchise/Specialty Code 4.0 | NONE | 0.6 | Prosthodontics; Periodontics | Very sparse; negligible |
| 372 | Franchise/Specialty Code 4.1 | NONE | 0.0 | — | Always empty |
| 373 | Franchise/Specialty Code 5.0 | NONE | 0.2 | — | Trace fill |
| 374 | Franchise/Specialty Code 5.1 | NONE | 0.0 | — | Always empty |
| 375 | Franchise/Specialty Code 6.0 | NONE | 0.0 | — | Always empty |
| 376 | Affiliated Records | HIGH | 0.0* | 000001; 000010 | *Sentinel "000000" = 100% fill; only 4 truly non-zero rows across 17k; when non-zero = count of affiliated DB records at corporate parent |
| 377 | Franchise/Specialty Code 6.1 | NONE | 0.0 | — | Always empty |
| 378 | Affiliated Locations | HIGH | 0.0* | 000001; 000010 | *Same sentinel pattern as Affiliated Records; when non-zero = location count under parent entity (e.g., Adv Family Dental = 10) |
| 379 | Federal Contractor | NONE | 100.0 | No | Always "No" in dental dataset |
| 380 | Census Block Group | NONE | 100.0 | 1; 2; 4 | Census geo unit, not ownership |
| 381 | Legal Name | HIGH | 10.2 | CAMERON F CROWE; DMD CONSULTING LLC; DENTAL 360 PULASKI 67 LLC | Registered legal entity name — differs from Company Name for stealth DSOs; LLC/PC pattern reveals corporate structure |
| 382 | Record Type | NONE | 100.0 | Verified | Data quality flag, not ownership |

---

## Notes on Sentinel Values

| Column | Sentinel Value | Meaning |
|--------|---------------|---------|
| `Affiliated Records` (376) | `000000` | No affiliated records data; TRUE non-zero = 4/17,042 rows (0.02%) |
| `Affiliated Locations` (378) | `000000` | Same; 4/17,042 rows non-zero |
| `Parent IUSA Number` (106) | `000000000` | No parent; non-zero = 260 rows (1.5%) |
| `Subsidiary IUSA Number` (107) | `000000000` | No subsidiary; non-zero = ~130 rows (0.8%) |
| `Corporate Employee Size Actual` (100) | `000000` | No corporate data; TRUE non-zero = 14 rows (0.1%) |
| `Corporate Sales Volume Actual` (102) | `$0` | No corporate data; TRUE non-zero = ~14 rows (0.1%) |
| `Fortune 1000 Ranking` (112) | `0000` | Not Fortune-ranked; no dental practices in Fortune 1000 |

---

## Header Spelling Warnings for Importer Dict

- **col 344:** `Advertising  Expenses` — TWO spaces between "Advertising" and "Expenses". Verbatim key must include double-space.
- **cols 141-142:** `Executive First Name 1` / `Executive Last Name 1` are EXACT DUPLICATES of cols 2-3 (`Executive First Name` / `Executive Last Name`). Import only one set.
- **col 365:** `Linked-In` (hyphenated, not "LinkedIn").
- **col 367:** `Franchise/Specialty Code 2.0` — the "2.0" suffix with decimal point, not "2" or "2.1".

---

*Generated 2026-06-07. Measured on 17,042 rows across 16 combined CSV exports.*
