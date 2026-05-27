"""
Preset watchlists.

Hardcoded constituent lists for common universes — S&P 500/100, Dow 30, Nasdaq 100,
sector ETFs, and per-GICS-sector slices drawn from the Russell 1000 (filtered for
$5+ price and 100k+ avg daily volume). These are point-in-time snapshots;
constituents drift as indices rebalance. The ``refresh.refresh_all`` function
regenerates them from Wikipedia + Schwab fundamentals.

Each preset has:
  - key:         stable identifier, used as the DB watchlist name when imported
  - label:       human-readable name shown in the UI
  - description: one-line hint
  - tickers:     the constituent list

Source snapshots taken 2026-05. Sector partitions follow GICS.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    description: str
    tickers: tuple[str, ...]
    category: str = "Index"


SP500: tuple[str, ...] = (
    "MMM", "AOS", "ABT", "ABBV", "ACN", "ADBE", "AMD", "AES", "AFL", "A",
    "APD", "ABNB", "AKAM", "ALB", "ARE", "ALGN", "ALLE", "LNT", "ALL", "GOOGL",
    "GOOG", "MO", "AMZN", "AMCR", "AEE", "AEP", "AXP", "AIG", "AMT", "AWK",
    "AMP", "AME", "AMGN", "APH", "ADI", "AON", "APA", "APO", "AAPL", "AMAT",
    "APP", "APTV", "ACGL", "ADM", "ARES", "ANET", "AJG", "AIZ", "T", "ATO",
    "ADSK", "ADP", "AZO", "AVB", "AVY", "AXON", "BKR", "BALL", "BAC", "BAX",
    "BDX", "BRK-B", "BBY", "TECH", "BIIB", "BLK", "BX", "XYZ", "BNY", "BA",
    "BKNG", "BSX", "BMY", "AVGO", "BR", "BRO", "BF-B", "BLDR", "BG", "BXP",
    "CHRW", "CDNS", "CPT", "CPB", "COF", "CAH", "CCL", "CARR", "CVNA", "CASY",
    "CAT", "CBOE", "CBRE", "CDW", "COR", "CNC", "CNP", "CF", "CRL", "SCHW",
    "CHTR", "CVX", "CMG", "CB", "CHD", "CIEN", "CI", "CINF", "CTAS", "CSCO",
    "C", "CFG", "CLX", "CME", "CMS", "KO", "CTSH", "COHR", "COIN", "CL",
    "CMCSA", "FIX", "CAG", "COP", "ED", "STZ", "CEG", "COO", "CPRT", "GLW",
    "CPAY", "CTVA", "CSGP", "COST", "CRH", "CRWD", "CCI", "CSX", "CMI", "CVS",
    "DHR", "DRI", "DDOG", "DVA", "DECK", "DE", "DELL", "DAL", "DVN", "DXCM",
    "FANG", "DLR", "DG", "DLTR", "D", "DPZ", "DASH", "DOV", "DOW", "DHI",
    "DTE", "DUK", "DD", "ETN", "EBAY", "SATS", "ECL", "EIX", "EW", "EA",
    "ELV", "EME", "EMR", "ETR", "EOG", "EPAM", "EQT", "EFX", "EQIX", "EQR",
    "ERIE", "ESS", "EL", "EG", "EVRG", "ES", "EXC", "EXE", "EXPE", "EXPD",
    "EXR", "XOM", "FFIV", "FDS", "FICO", "FAST", "FRT", "FDX", "FIS", "FITB",
    "FSLR", "FE", "FISV", "F", "FTNT", "FTV", "FOXA", "FOX", "BEN", "FCX",
    "GRMN", "IT", "GE", "GEHC", "GEV", "GEN", "GNRC", "GD", "GIS", "GM",
    "GPC", "GILD", "GPN", "GL", "GDDY", "GS", "HAL", "HIG", "HAS", "HCA",
    "DOC", "HSIC", "HSY", "HPE", "HLT", "HD", "HON", "HRL", "HST", "HWM",
    "HPQ", "HUBB", "HUM", "HBAN", "HII", "IBM", "IEX", "IDXX", "ITW", "INCY",
    "IR", "PODD", "INTC", "IBKR", "ICE", "IFF", "IP", "INTU", "ISRG", "IVZ",
    "INVH", "IQV", "IRM", "JBHT", "JBL", "JKHY", "J", "JNJ", "JCI", "JPM",
    "KVUE", "KDP", "KEY", "KEYS", "KMB", "KIM", "KMI", "KKR", "KLAC", "KHC",
    "KR", "LHX", "LH", "LRCX", "LVS", "LDOS", "LEN", "LII", "LLY", "LIN",
    "LYV", "LMT", "L", "LOW", "LULU", "LITE", "LYB", "MTB", "MPC", "MAR",
    "MRSH", "MLM", "MAS", "MA", "MKC", "MCD", "MCK", "MDT", "MRK", "META",
    "MET", "MTD", "MGM", "MCHP", "MU", "MSFT", "MAA", "MRNA", "TAP", "MDLZ",
    "MPWR", "MNST", "MCO", "MS", "MOS", "MSI", "MSCI", "NDAQ", "NTAP", "NFLX",
    "NEM", "NWSA", "NWS", "NEE", "NKE", "NI", "NDSN", "NSC", "NTRS", "NOC",
    "NCLH", "NRG", "NUE", "NVDA", "NVR", "NXPI", "ORLY", "OXY", "ODFL", "OMC",
    "ON", "OKE", "ORCL", "OTIS", "PCAR", "PKG", "PLTR", "PANW", "PSKY", "PH",
    "PAYX", "PYPL", "PNR", "PEP", "PFE", "PCG", "PM", "PSX", "PNW", "PNC",
    "POOL", "PPG", "PPL", "PFG", "PG", "PGR", "PLD", "PRU", "PEG", "PTC",
    "PSA", "PHM", "PWR", "QCOM", "DGX", "Q", "RL", "RJF", "RTX", "O",
    "REG", "REGN", "RF", "RSG", "RMD", "RVTY", "HOOD", "ROK", "ROL", "ROP",
    "ROST", "RCL", "SPGI", "CRM", "SNDK", "SBAC", "SLB", "STX", "SRE", "NOW",
    "SHW", "SPG", "SWKS", "SJM", "SW", "SNA", "SOLV", "SO", "LUV", "SWK",
    "SBUX", "STT", "STLD", "STE", "SYK", "SMCI", "SYF", "SNPS", "SYY", "TMUS",
    "TROW", "TTWO", "TPR", "TRGP", "TGT", "TEL", "TDY", "TER", "TSLA", "TXN",
    "TPL", "TXT", "TMO", "TJX", "TKO", "TTD", "TSCO", "TT", "TDG", "TRV",
    "TRMB", "TFC", "TYL", "TSN", "USB", "UBER", "UDR", "ULTA", "UNP", "UAL",
    "UPS", "URI", "UNH", "UHS", "VLO", "VEEV", "VTR", "VLTO", "VRSN", "VRSK",
    "VZ", "VRTX", "VRT", "VTRS", "VICI", "V", "VST", "VMC", "WRB", "GWW",
    "WAB", "WMT", "DIS", "WBD", "WM", "WAT", "WEC", "WFC", "WELL", "WST",
    "WDC", "WY", "WSM", "WMB", "WTW", "WDAY", "WYNN", "XEL", "XYL", "YUM",
    "ZBRA", "ZBH", "ZTS",
)

SP100: tuple[str, ...] = (
    "NVDA", "GOOGL", "GOOG", "AAPL", "MSFT", "AMZN", "AVGO", "TSLA", "META", "BRK-B",
    "MU", "LLY", "WMT", "AMD", "JPM", "XOM", "INTC", "JNJ", "ORCL", "CSCO",
    "COST", "MA", "CAT", "LRCX", "ABBV", "NFLX", "CVX", "BAC", "KO", "AMAT",
    "UNH", "PG", "GE", "PLTR", "HD", "MS", "MRK", "GS", "TXN", "PM",
    "GEV", "KLAC", "IBM", "QCOM", "RTX", "LIN", "WFC", "SNDK", "AXP", "C",
    "TMUS", "VZ", "PEP", "PANW", "MCD", "ADI", "DELL", "ANET", "STX", "APP",
    "AMGN", "NEE", "WDC", "DIS", "BA", "TJX", "T", "APH", "GILD", "TMO",
    "BLK", "UNP", "CRWD", "GLW", "ETN", "WELL", "ISRG", "PFE", "ABT", "SCHW",
    "CRM", "HON", "BX", "UBER", "DE", "COP", "PLD", "BKNG", "CB", "SPGI",
    "LMT", "LOW", "DHR", "VRT", "MO", "BMY", "SYK", "COF", "CVS", "SBUX",
)

DOW30: tuple[str, ...] = (
    "MMM", "AXP", "AMGN", "AMZN", "AAPL", "BA", "CAT", "CVX", "CSCO", "KO",
    "DIS", "GS", "HD", "HON", "IBM", "JNJ", "JPM", "MCD", "MRK", "MSFT",
    "NKE", "NVDA", "PG", "CRM", "SHW", "TRV", "UNH", "VZ", "V", "WMT",
)

NDX100: tuple[str, ...] = (
    "ADBE", "AMD", "ABNB", "ALNY", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN", "ADI",
    "AAPL", "AMAT", "APP", "ARM", "ASML", "ADSK", "ADP", "AXON", "BKR", "BKNG",
    "AVGO", "CDNS", "CHTR", "CTAS", "CSCO", "CCEP", "CTSH", "CMCSA", "CEG", "CPRT",
    "COST", "CRWD", "CSX", "DDOG", "DXCM", "FANG", "DASH", "EA", "EXC", "FAST",
    "FER", "FTNT", "GEHC", "GILD", "HON", "IDXX", "INSM", "INTC", "INTU", "ISRG",
    "KDP", "KLAC", "KHC", "LRCX", "LIN", "LITE", "MAR", "MRVL", "MELI", "META",
    "MCHP", "MU", "MSFT", "MSTR", "MDLZ", "MPWR", "MNST", "NFLX", "NVDA", "NXPI",
    "ORLY", "ODFL", "PCAR", "PLTR", "PANW", "PAYX", "PYPL", "PDD", "PEP", "QCOM",
    "REGN", "ROP", "ROST", "SNDK", "STX", "SHOP", "SBUX", "SNPS", "TMUS", "TTWO",
    "TSLA", "TXN", "TRI", "VRSK", "VRTX", "WMT", "WBD", "WDC", "WDAY", "XEL",
    "ZS",
)

SECTOR_ETFS: tuple[str, ...] = (
    "XLK",  # Tech
    "XLV",  # Healthcare
    "XLF",  # Financials
    "XLY",  # Consumer Discretionary
    "XLP",  # Consumer Staples
    "XLE",  # Energy
    "XLI",  # Industrials
    "XLB",  # Materials
    "XLU",  # Utilities
    "XLRE", # Real Estate
    "XLC",  # Communication Services
    "SPY", "QQQ", "IWM", "DIA",  # Broad market
)

SECTOR_TECH: tuple[str, ...] = (
    "AAPL", "ACN", "ADBE", "ADI", "ADSK", "AFRM", "AKAM", "ALAB", "ALGM", "AMAT",
    "AMD", "AMKR", "ANET", "APH", "APP", "APPF", "ARW", "AUR", "AVGO", "AVT",
    "BILL", "BSY", "CDNS", "CDW", "CGNX", "CIEN", "CNXC", "COHR", "CRCL", "CRM",
    "CRUS", "CRWD", "CSCO", "CTSH", "DBX", "DDOG", "DELL", "DLB", "DOCU", "DOX",
    "DT", "DV", "DXC", "ENPH", "ENTG", "EPAM", "ESTC", "FFIV", "FICO", "FLEX",
    "FOUR", "FSLR", "FTNT", "GDDY", "GEN", "GFS", "GLOB", "GLW", "GTLB", "GWRE",
    "HPE", "HPQ", "HUBS", "IBM", "INGM", "INTC", "INTU", "IOT", "IPGP", "IT",
    "JBL", "KD", "KEYS", "KLAC", "LFUS", "LITE", "LRCX", "LSCC", "MANH", "MCHP",
    "MDB", "MKSI", "MPWR", "MRVL", "MSFT", "MSI", "MSTR", "MTSI", "MU", "NCNO",
    "NET", "NOW", "NTAP", "NTNX", "NVDA", "OKTA", "OLED", "ON", "ONTO", "ORCL",
)

SECTOR_HEALTHCARE: tuple[str, ...] = (
    "A", "ABBV", "ABT", "ACHC", "ALGN", "ALNY", "AMGN", "AVTR", "BAX", "BDX",
    "BIIB", "BIO", "BMRN", "BMY", "BRKR", "BSX", "CAH", "CAI", "CERT", "CHE",
    "CI", "CNC", "COO", "COR", "CORT", "CRL", "CVS", "DGX", "DHR", "DOCS",
    "DVA", "DXCM", "EHC", "ELAN", "ELV", "EW", "EXEL", "GEHC", "GILD", "GMED",
    "HALO", "HCA", "HSIC", "HUM", "IDXX", "ILMN", "INCY", "INSM", "INSP", "IONS",
    "IQV", "ISRG", "JAZZ", "JNJ", "LH", "LLY", "MASI", "MCK", "MDLN", "MDT",
    "MEDP", "MOH", "MRK", "MRNA", "MTD", "NBIX", "NTRA", "NVST", "OGN", "PEN",
    "PFE", "PODD", "PRGO", "QGEN", "RARE", "REGN", "RGEN", "RMD", "ROIV", "RPRX",
    "RVMD", "RVTY", "SHC", "SMMT", "SOLV", "SRPT", "STE", "SYK", "TECH", "TEM",
    "TFX", "THC", "TMO", "UHS", "UNH", "UTHR", "VEEV", "VKTX", "VRTX", "VTRS",
)

SECTOR_FINANCIALS: tuple[str, ...] = (
    "ACGL", "AFG", "AFL", "AGNC", "AGO", "AIG", "AIZ", "AJG", "ALL", "ALLY",
    "AMG", "AMP", "AON", "APO", "ARES", "AXP", "AXS", "BAC", "BAM", "BEN",
    "BHF", "BLK", "BLSH", "BNY", "BOKF", "BPOP", "BRO", "BX", "C", "CACC",
    "CB", "CBC", "CBOE", "CBSH", "CFG", "CFR", "CG", "CINF", "CME", "CNA",
    "COF", "COIN", "COLB", "CPAY", "EEFT", "EG", "EQH", "EVR", "EWBC", "FAF",
    "FDS", "FHB", "FHN", "FIGR", "FIS", "FISV", "FITB", "FNB", "FNF", "FRHC",
    "GL", "GPN", "GS", "HBAN", "HIG", "HLI", "HLNE", "HOOD", "IBKR", "ICE",
    "IVZ", "JEF", "JHG", "JKHY", "JPM", "KEY", "KKR", "KMPR", "KNSL", "L",
    "LAZ", "LNC", "LPLA", "MA", "MCO", "MET", "MKTX", "MORN", "MRSH", "MS",
    "MSCI", "MTB", "MTG", "NDAQ", "NLY", "NTRS", "NU", "OMF", "ORI", "OWL",
)

SECTOR_CONSUMER_DISC: tuple[str, ...] = (
    "ABNB", "ADT", "AMZN", "AN", "APTV", "ARMK", "AS", "AZO", "BBWI", "BBY",
    "BC", "BFAM", "BIRK", "BKNG", "BLD", "BROS", "BURL", "BWA", "BYD", "CAVA",
    "CCL", "CHDN", "CHH", "CHWY", "CMG", "COLM", "CPNG", "CROX", "CVNA", "CZR",
    "DASH", "DDS", "DECK", "DHI", "DKNG", "DKS", "DPZ", "DRI", "DUOL", "EBAY",
    "ETSY", "EXPE", "F", "FIVE", "FLUT", "FND", "GAP", "GM", "GME", "GNTX",
    "GPC", "GRMN", "H", "HAS", "HD", "HLT", "HOG", "HRB", "KMX", "LAD",
    "LCID", "LEA", "LEN", "LKQ", "LOPE", "LOW", "LULU", "LVS", "M", "MAR",
    "MAT", "MCD", "MGM", "MHK", "MRP", "MTN", "MUSA", "NCLH", "NKE", "OLLI",
    "ONON", "ORLY", "PAG", "PENN", "PHM", "PLNT", "POOL", "PVH", "QS", "QSR",
    "RCL", "RH", "RIVN", "RL", "ROST", "SBUX", "SCI", "SGI", "SN", "THO",
)

SECTOR_CONSUMER_STAPLES: tuple[str, ...] = (
    "ACI", "ADM", "BG", "BJ", "BRBR", "CAG", "CART", "CASY", "CELH", "CHD",
    "CL", "CLX", "COKE", "COST", "CPB", "DAR", "DG", "DLTR", "EL", "ELF",
    "FLO", "FRPT", "GIS", "HRL", "HSY", "INGR", "KDP", "KHC", "KMB", "KO",
    "KR", "KVUE", "LW", "MDLZ", "MKC", "MNST", "MO", "PEP", "PFGC", "PG",
    "PM", "POST", "PPC", "PRMB", "REYN", "SAM", "SFD", "SFM", "SJM", "STZ",
    "SYY", "TAP", "TGT", "TSN", "USFD", "WMT",
)

SECTOR_ENERGY: tuple[str, ...] = (
    "AM", "APA", "AR", "BKR", "CHRD", "COP", "CVX", "DINO", "DTM", "DVN",
    "EOG", "EQT", "EXE", "FANG", "FTI", "HAL", "KMI", "LNG", "MPC", "MTDR",
    "NOV", "OKE", "OVV", "OXY", "PR", "PSX", "RRC", "SLB", "TPL", "TRGP",
    "VLO", "VNOM", "WFRD", "WMB", "XOM",
)

SECTOR_INDUSTRIALS: tuple[str, ...] = (
    "AAL", "AAON", "ACM", "ADP", "AGCO", "AIT", "ALK", "ALLE", "ALSN", "AME",
    "AMTM", "AOS", "APG", "ATI", "AWI", "AXON", "AYI", "BA", "BAH", "BLDR",
    "BR", "BWXT", "CACI", "CAR", "CARR", "CAT", "CHRW", "CLH", "CMI", "CNH",
    "CNM", "CPRT", "CR", "CSL", "CSX", "CTAS", "CW", "CXT", "DAL", "DCI",
    "DE", "DOV", "DRS", "ECG", "EFX", "EME", "EMR", "ESAB", "ETN", "EXLS",
    "EXPD", "FAST", "FBIN", "FCN", "FDX", "FERG", "FIX", "FLS", "FTAI", "FTV",
    "G", "GD", "GE", "GEV", "GGG", "GNRC", "GTES", "GWW", "GXO", "HAYW",
    "HEI", "HII", "HON", "HUBB", "HWM", "HXL", "IEX", "IR", "ITT", "ITW",
    "J", "JBHT", "JCI", "KBR", "KEX", "KNX", "KRMN", "LDOS", "LECO", "LHX",
    "LII", "LMT", "LOAR", "LSTR", "LUV", "LYFT", "MAN", "MAS", "MIDD", "MLI",
)

SECTOR_MATERIALS: tuple[str, ...] = (
    "AA", "ALB", "AMCR", "APD", "ASH", "ATR", "AU", "AVY", "AXTA", "BALL",
    "CCK", "CE", "CF", "CLF", "CRH", "CRS", "CTVA", "DD", "DOW", "ECL",
    "EMN", "ESI", "EXP", "FCX", "FMC", "GPK", "HUN", "IFF", "IP", "JHX",
    "LIN", "LPX", "LYB", "MLM", "MOS", "MP", "NEM", "NEU", "NUE", "OLN",
    "PKG", "PPG", "RGLD", "RPM", "RS", "SCCO", "SHW", "SLGN", "SMG", "SOLS",
    "SON", "STLD", "SW", "VMC", "VVV", "WLK",
)

SECTOR_UTILITIES: tuple[str, ...] = (
    "AEE", "AEP", "AES", "ATO", "AWK", "BEPC", "CEG", "CMS", "CNP", "CWEN",
    "D", "DTE", "DUK", "ED", "EIX", "ES", "ETR", "EVRG", "EXC", "FE",
    "IDA", "LNT", "MDU", "NEE", "NFG", "NI", "NRG", "OGE", "PCG", "PEG",
    "PNW", "PPL", "SO", "SRE", "TLN", "UGI", "VST", "WEC", "WTRG", "XEL",
)

SECTOR_REAL_ESTATE: tuple[str, ...] = (
    "ADC", "AMH", "AMT", "ARE", "AVB", "BRX", "BXP", "CBRE", "CCI", "COLD",
    "CPT", "CSGP", "CUBE", "CUZ", "DLR", "DOC", "EGP", "ELS", "EPR", "EQIX",
    "EQR", "ESS", "EXR", "FR", "FRMI", "FRT", "GLPI", "HHH", "HIW", "HR",
    "HST", "INVH", "IRM", "JLL", "KIM", "KRC", "LAMR", "LINE", "MAA", "MPT",
    "NNN", "NSA", "O", "OHI", "PK", "PLD", "PSA", "REG", "REXR", "RYN",
    "SBAC", "SPG", "STAG", "SUI", "UDR", "VICI", "VNO", "VTR", "WELL", "WPC",
    "WY", "Z", "ZG",
)

SECTOR_COMMS: tuple[str, ...] = (
    "ASTS", "CHTR", "CMCSA", "DIS", "DJT", "EA", "FOX", "FOXA", "FWONA", "FWONK",
    "GLIBK", "GOOG", "GOOGL", "IAC", "IRDM", "LBRDA", "LBRDK", "LBTYA", "LBTYK", "LLYVA",
    "LLYVK", "LYV", "META", "MSGS", "MTCH", "NFLX", "NIQ", "NWS", "NWSA", "NXST",
    "NYT", "OMC", "PINS", "RBLX", "RDDT", "ROKU", "SIRI", "SPOT", "T", "TIGO",
    "TKO", "TMUS", "TTD", "TTWO", "VSNT", "VZ", "WBD",
)

PRESETS: tuple[Preset, ...] = (
    Preset(
        key="sp500",
        label="S&P 500",
        description="All ~500 S&P 500 constituents. Broadest preset; full-universe scans take a few minutes.",
        tickers=SP500,
        category="Index",
    ),
    Preset(
        key="sp100",
        label="S&P 100",
        description="100 largest U.S. companies by market cap.",
        tickers=SP100,
        category="Index",
    ),
    Preset(
        key="dow30",
        label="Dow Jones 30",
        description="All 30 components of the Dow Jones Industrial Average.",
        tickers=DOW30,
        category="Index",
    ),
    Preset(
        key="ndx100",
        label="Nasdaq 100",
        description="All 100 non-financial Nasdaq listings — tech-heavy, high beta.",
        tickers=NDX100,
        category="Index",
    ),
    Preset(
        key="sector_etfs",
        label="Sector ETFs + broad market",
        description="11 SPDR sector ETFs plus SPY/QQQ/IWM/DIA for macro reads.",
        tickers=SECTOR_ETFS,
        category="ETF",
    ),
    Preset(
        key="sector_tech",
        label="Sector — Technology",
        description="Top GICS Information Technology names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_TECH,
        category="Sector",
    ),
    Preset(
        key="sector_healthcare",
        label="Sector — Healthcare",
        description="Top GICS Healthcare names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_HEALTHCARE,
        category="Sector",
    ),
    Preset(
        key="sector_financials",
        label="Sector — Financials",
        description="Top GICS Financials names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_FINANCIALS,
        category="Sector",
    ),
    Preset(
        key="sector_consumer_disc",
        label="Sector — Consumer Discretionary",
        description="Top GICS Consumer Discretionary names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_CONSUMER_DISC,
        category="Sector",
    ),
    Preset(
        key="sector_consumer_staples",
        label="Sector — Consumer Staples",
        description="Top GICS Consumer Staples names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_CONSUMER_STAPLES,
        category="Sector",
    ),
    Preset(
        key="sector_energy",
        label="Sector — Energy",
        description="Top GICS Energy names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_ENERGY,
        category="Sector",
    ),
    Preset(
        key="sector_industrials",
        label="Sector — Industrials",
        description="Top GICS Industrials names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_INDUSTRIALS,
        category="Sector",
    ),
    Preset(
        key="sector_materials",
        label="Sector — Materials",
        description="Top GICS Materials names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_MATERIALS,
        category="Sector",
    ),
    Preset(
        key="sector_utilities",
        label="Sector — Utilities",
        description="Top GICS Utilities names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_UTILITIES,
        category="Sector",
    ),
    Preset(
        key="sector_real_estate",
        label="Sector — Real Estate",
        description="Top GICS Real Estate names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_REAL_ESTATE,
        category="Sector",
    ),
    Preset(
        key="sector_comms",
        label="Sector — Communication Services",
        description="Top GICS Communication Services names from Russell 1000 (US large+mid cap), filtered for liquidity ($5+ price, 100k+ avg volume).",
        tickers=SECTOR_COMMS,
        category="Sector",
    ),
)

PRESETS_BY_KEY: dict[str, Preset] = {p.key: p for p in PRESETS}


def by_category() -> dict[str, list[Preset]]:
    grouped: dict[str, list[Preset]] = {}
    for p in PRESETS:
        grouped.setdefault(p.category, []).append(p)
    return grouped
