/**
 * Shared dropdown option lists for CRM / Memberships / Marketing / Staffing.
 *
 * Iter 216h195 — Wave 2 of Lee's "dropdowns everywhere" audit. Same
 * rationale as `operationsDropdowns.js`: kill dirty data caused by
 * free-text fields ("Hotel Spa" vs "hotel-spa" vs "Hotel-spa" vs
 * "spa"), keep reports clean, speed up data entry.
 *
 * Companion file:
 *   - operationsDropdowns.js (equipment / SLA / location enums)
 *
 * Every list keeps an "Other" / "Other (specify)" escape hatch so the
 * form still accepts edge cases — selecting it should reveal a free
 * text input in the host form (left to each caller).
 */

// UK fitness-industry sectors (Tier A item #1). Order = rough frequency
// in the Pulse Fitness sales pipeline so the most-common picks are top.
export const FITNESS_SECTOR_OPTIONS = [
  'Gym Chain',
  'Independent Gym',
  'Boutique Studio',
  'Hotel Health Club',
  'Hotel / Resort Spa',
  'Council / Public Leisure Centre',
  'Corporate Wellness',
  'University / Education',
  'Healthcare / Rehab Clinic',
  'Sports Club',
  'Personal Training Studio',
  'Crossfit / Functional Box',
  'Yoga / Pilates Studio',
  'Martial Arts / Combat Sports',
  'Swimming Pool',
  'Health & Wellness Spa',
  'Other',
];

// UK counties (Tier A item #3). Covers historic + ceremonial + Greater
// London + Welsh / Scottish / NI. Used as suggestion list — operator
// can still type a bespoke value via the datalist fallback.
export const UK_COUNTIES = [
  'Aberdeenshire', 'Angus', 'Argyll and Bute', 'Bedfordshire',
  'Berkshire', 'Borders', 'Bristol', 'Buckinghamshire',
  'Cambridgeshire', 'Cardiff', 'Carmarthenshire', 'Ceredigion',
  'Cheshire', 'Cornwall', 'County Antrim', 'County Armagh',
  'County Down', 'County Fermanagh', 'County Londonderry', 'County Tyrone',
  'Cumbria', 'Denbighshire', 'Derbyshire', 'Devon',
  'Dorset', 'Dumfries and Galloway', 'Durham', 'East Lothian',
  'East Riding of Yorkshire', 'East Sussex', 'Edinburgh', 'Essex',
  'Falkirk', 'Fife', 'Flintshire', 'Glasgow',
  'Gloucestershire', 'Greater London', 'Greater Manchester',
  'Gwynedd', 'Hampshire', 'Herefordshire', 'Hertfordshire',
  'Highland', 'Isle of Anglesey', 'Isle of Man', 'Isle of Wight',
  'Kent', 'Lancashire', 'Leicestershire', 'Lincolnshire',
  'Merseyside', 'Mid Glamorgan', 'Midlothian', 'Monmouthshire',
  'Moray', 'Newport', 'Norfolk', 'North Ayrshire',
  'North Lanarkshire', 'North Yorkshire', 'Northamptonshire',
  'Northumberland', 'Nottinghamshire', 'Oxfordshire', 'Perth and Kinross',
  'Powys', 'Renfrewshire', 'Rhondda Cynon Taf', 'Rutland',
  'Shetland', 'Shropshire', 'Somerset', 'South Ayrshire',
  'South Glamorgan', 'South Lanarkshire', 'South Yorkshire', 'Staffordshire',
  'Stirling', 'Suffolk', 'Surrey', 'Swansea',
  'Tyne and Wear', 'Vale of Glamorgan', 'Warwickshire', 'West Dunbartonshire',
  'West Glamorgan', 'West Lothian', 'West Midlands', 'West Sussex',
  'West Yorkshire', 'Wiltshire', 'Worcestershire', 'Wrexham',
];

// Practical country list (Tier A items #2 + #4). UK + most-common
// international markets first, then alphabetical rest of the world.
// Use as both <datalist> fallback (preserves free-text) AND a typeahead
// trigger in the host component.
export const COUNTRIES = [
  // Pulse Fitness / Pulse Fitness primary markets
  'United Kingdom',
  'Ireland',
  'France',
  'Germany',
  'Spain',
  'Netherlands',
  'United States',
  'Canada',
  'Australia',
  'New Zealand',
  'United Arab Emirates',
  'Saudi Arabia',
  'Qatar',
  'South Africa',
  // Rest of the world (alphabetical)
  'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola', 'Argentina',
  'Armenia', 'Austria', 'Azerbaijan', 'Bahamas', 'Bahrain', 'Bangladesh',
  'Barbados', 'Belarus', 'Belgium', 'Belize', 'Benin', 'Bhutan',
  'Bolivia', 'Bosnia and Herzegovina', 'Botswana', 'Brazil', 'Brunei',
  'Bulgaria', 'Burkina Faso', 'Burundi', 'Cambodia', 'Cameroon',
  'Cape Verde', 'Central African Republic', 'Chad', 'Chile', 'China',
  'Colombia', 'Comoros', 'Costa Rica', 'Croatia', 'Cuba', 'Cyprus',
  'Czech Republic', 'Denmark', 'Djibouti', 'Dominican Republic', 'Ecuador',
  'Egypt', 'El Salvador', 'Equatorial Guinea', 'Eritrea', 'Estonia',
  'Eswatini', 'Ethiopia', 'Fiji', 'Finland', 'Gabon', 'Gambia', 'Georgia',
  'Ghana', 'Greece', 'Grenada', 'Guatemala', 'Guinea', 'Guyana', 'Haiti',
  'Honduras', 'Hungary', 'Iceland', 'India', 'Indonesia', 'Iran', 'Iraq',
  'Israel', 'Italy', 'Ivory Coast', 'Jamaica', 'Japan', 'Jordan',
  'Kazakhstan', 'Kenya', 'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia',
  'Lebanon', 'Lesotho', 'Liberia', 'Libya', 'Liechtenstein', 'Lithuania',
  'Luxembourg', 'Madagascar', 'Malawi', 'Malaysia', 'Maldives', 'Mali',
  'Malta', 'Mauritania', 'Mauritius', 'Mexico', 'Moldova', 'Monaco',
  'Mongolia', 'Montenegro', 'Morocco', 'Mozambique', 'Myanmar',
  'Namibia', 'Nepal', 'Nicaragua', 'Niger', 'Nigeria', 'North Macedonia',
  'Norway', 'Oman', 'Pakistan', 'Panama', 'Papua New Guinea', 'Paraguay',
  'Peru', 'Philippines', 'Poland', 'Portugal', 'Romania', 'Russia',
  'Rwanda', 'Samoa', 'San Marino', 'Senegal', 'Serbia', 'Seychelles',
  'Sierra Leone', 'Singapore', 'Slovakia', 'Slovenia', 'Somalia',
  'South Korea', 'South Sudan', 'Sri Lanka', 'Sudan', 'Suriname',
  'Sweden', 'Switzerland', 'Syria', 'Taiwan', 'Tajikistan', 'Tanzania',
  'Thailand', 'Togo', 'Trinidad and Tobago', 'Tunisia', 'Turkey',
  'Turkmenistan', 'Uganda', 'Ukraine', 'Uruguay', 'Uzbekistan',
  'Vanuatu', 'Vatican City', 'Venezuela', 'Vietnam', 'Yemen', 'Zambia',
  'Zimbabwe',
  'Other',
];

// Lead-source taxonomy (Tier A item #6). Tracks where deals come from so
// reports can show conversion rate by source. Keep limited to avoid the
// classic "we have 47 sources but no insight" trap.
export const LEAD_SOURCE_OPTIONS = [
  { value: 'website',         label: 'Website' },
  { value: 'referral',        label: 'Referral' },
  { value: 'cold_outreach',   label: 'Cold Outreach' },
  { value: 'trade_show',      label: 'Trade Show / Event' },
  { value: 'partner',         label: 'Partner' },
  { value: 'linkedin',        label: 'LinkedIn' },
  { value: 'inbound_call',    label: 'Inbound Call' },
  { value: 'email_campaign',  label: 'Email Campaign' },
  { value: 'walk_in',         label: 'Walk-in' },
  { value: 'existing_account', label: 'Existing Customer' },
  { value: 'other',           label: 'Other' },
];

// Emergency-contact relationship (Tier A item #7). Used in both
// Memberships member profile and Staffing HR.
export const RELATIONSHIP_OPTIONS = [
  'Spouse / Civil Partner',
  'Partner',
  'Parent',
  'Sibling',
  'Child',
  'Friend',
  'Guardian',
  'Carer',
  'Other',
];

// CRM Task types (Tier B item #8).
export const CRM_TASK_TYPE_OPTIONS = [
  { value: 'call',       label: 'Call' },
  { value: 'meeting',    label: 'Meeting' },
  { value: 'follow_up',  label: 'Follow-up' },
  { value: 'email',      label: 'Email' },
  { value: 'demo',       label: 'Demo' },
  { value: 'proposal',   label: 'Proposal / Quote' },
  { value: 'site_visit', label: 'Site Visit' },
  { value: 'admin',      label: 'Admin / Internal' },
  { value: 'other',      label: 'Other' },
];

// CRM Task priorities (Tier B item #8 continued).
export const CRM_TASK_PRIORITY_OPTIONS = [
  { value: 'low',     label: 'Low' },
  { value: 'medium',  label: 'Medium' },
  { value: 'high',    label: 'High' },
  { value: 'urgent',  label: 'Urgent' },
];

// Currency (Tier B item #11). Real list — we surface GBP first because
// that's the Pulse Fitness / Pulse Fitness primary market.
export const CURRENCY_OPTIONS = [
  { value: 'GBP', label: '£ GBP (Pound Sterling)' },
  { value: 'EUR', label: '€ EUR (Euro)' },
  { value: 'USD', label: '$ USD (US Dollar)' },
  { value: 'AED', label: 'AED (UAE Dirham)' },
  { value: 'SAR', label: 'SAR (Saudi Riyal)' },
  { value: 'ZAR', label: 'R ZAR (South African Rand)' },
  { value: 'AUD', label: '$ AUD (Australian Dollar)' },
  { value: 'CAD', label: '$ CAD (Canadian Dollar)' },
  { value: 'CHF', label: 'CHF (Swiss Franc)' },
  { value: 'NOK', label: 'NOK (Norwegian Krone)' },
  { value: 'SEK', label: 'SEK (Swedish Krona)' },
  { value: 'DKK', label: 'DKK (Danish Krone)' },
];

// Meeting locations (Tier C — replaced the free-text input with a
// suggestion list so reports can group e.g. "% of demos held on Teams").
export const MEETING_LOCATION_PRESETS = [
  'Microsoft Teams',
  'Zoom',
  'Google Meet',
  'Phone Call',
  'On-site at customer',
  'On-site at our office',
  'Trade show stand',
  'Other',
];

// HR Contract types (existing constant in HRTab.js — exported here for
// reuse across the Staffing module).
export const CONTRACT_TYPE_OPTIONS = [
  '',                  // unknown / not set
  'permanent_ft',
  'permanent_pt',
  'fixed_term',
  'zero_hours',
  'casual',
  'apprentice',
  'self_employed',
];
