# TLS scanners on C2's endpoints

sslyze 6.3.1, testssl.sh version 3.2.5 from https://testssl.sh/; 2026-11-12T04:25:50Z to 2026-11-12T04:35:55Z; commit 99aeebb7; failed: none.

## 9 endpoint(s): 172.30.0.100:8101, 172.30.0.100:8102, 10.0.0.228:8105, 172.30.0.100:8201, 172.30.0.100:8202, 10.0.0.228:8205, 172.30.0.100:8301, 172.30.0.100:8302, 10.0.0.228:8305

- Versions accepted: TLS 1.2, TLS 1.3
  - TLS 1.2: TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256, TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384, TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384, TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256, TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256
  - TLS 1.3: TLS_CHACHA20_POLY1305_SHA256, TLS_AES_256_GCM_SHA384, TLS_AES_128_GCM_SHA256
- sslyze vulnerability checks: none positive
- testssl.sh grade B; findings rated MEDIUM or above:
  - CRITICAL `cert_chain_of_trust`: failed (chain incomplete).
  - HIGH `cert_revocation`: Neither CRL nor OCSP URI provided
  - MEDIUM `security_headers`: --
- LOW: `DNS_CAArecord`, `FS_KEMs`, `HSTS`, `LUCKY13`, `cipher-tls1_2_xc027`, `cipher-tls1_2_xc028`, `cipherlist_OBSOLETED`

Neither scanner has a check on the sizes or timing of the encrypted traffic: what a2a-leakcheck audits is outside what they test.
