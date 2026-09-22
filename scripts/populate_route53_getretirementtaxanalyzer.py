#!/usr/bin/env python3
"""Populate Route 53 hosted zone for getretirementtaxanalyzer.com with all zone records.
Includes the updated SPF record authorizing Microsoft 365 Exchange, GoDaddy, and AWS SES.
"""

import logging

from cocli.core.reporting import get_boto3_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HOSTED_ZONE_ID = "Z10138391FG0Z7SU19Y31"
DOMAIN = "getretirementtaxanalyzer.com."
PROFILE = "westmonroe-support"

CHANGES = [
    # 1. Apex A records (GitHub Pages)
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": DOMAIN,
            "Type": "A",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": "185.199.108.153"},
                {"Value": "185.199.109.153"},
                {"Value": "185.199.110.153"},
                {"Value": "185.199.111.153"},
            ],
        },
    },
    # 2. Apex TXT records (M365 tenant, Google site verification, Updated SPF)
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": DOMAIN,
            "Type": "TXT",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": '"NETORG19853208.onmicrosoft.com"'},
                {"Value": '"google-site-verification=HXwXUkRIRzSFt9Sff1Ho2CDiwYSvsIuNpeMeav-j7tM"'},
                {"Value": '"v=spf1 include:spf.protection.outlook.com include:secureserver.net include:amazonses.com ~all"'},
            ],
        },
    },
    # 3. Apex MX record (Microsoft 365 Exchange Online)
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": DOMAIN,
            "Type": "MX",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": "0 getretirementtaxanalyzer-com.mail.protection.outlook.com."},
            ],
        },
    },
    # 4. DMARC TXT record
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"_dmarc.{DOMAIN}",
            "Type": "TXT",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": '"v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;"'},
            ],
        },
    },
    # 5. GitHub Pages Challenge
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"_github-pages-challenge-bizkite-co.{DOMAIN}",
            "Type": "TXT",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": '"55d0ee55fd2fc779400224ce635974"'},
            ],
        },
    },
    # 6. Bounce MX and SPF records for SES
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"bounce.{DOMAIN}",
            "Type": "MX",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": "10 feedback-smtp.us-west-1.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"bounce.{DOMAIN}",
            "Type": "TXT",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": '"v=spf1 include:amazonses.com ~all"'},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"bounce.outreach.{DOMAIN}",
            "Type": "MX",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": "10 feedback-smtp.us-west-1.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"bounce.outreach.{DOMAIN}",
            "Type": "TXT",
            "TTL": 300,
            "ResourceRecords": [
                {"Value": '"v=spf1 include:amazonses.com ~all"'},
            ],
        },
    },
    # 7. SES DKIM CNAME records
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"bkzivi4paugnhx62wawhrri7kug57xl2._domainkey.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 1800,
            "ResourceRecords": [
                {"Value": "bkzivi4paugnhx62wawhrri7kug57xl2.dkim.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"cexklkq4ln2tgppxip4dimeervdelfj6._domainkey.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 1800,
            "ResourceRecords": [
                {"Value": "cexklkq4ln2tgppxip4dimeervdelfj6.dkim.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"oklaab4faq4zqtzfo5izzltpkds7qbfs._domainkey.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 1800,
            "ResourceRecords": [
                {"Value": "oklaab4faq4zqtzfo5izzltpkds7qbfs.dkim.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"bg2ntnhbnemvef2yhcybayb3x2il2wq6._domainkey.outreach.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 1800,
            "ResourceRecords": [
                {"Value": "bg2ntnhbnemvef2yhcybayb3x2il2wq6.dkim.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"oik5dv2rtrgz4tnscecsx2uzuw5azltl._domainkey.outreach.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 1800,
            "ResourceRecords": [
                {"Value": "oik5dv2rtrgz4tnscecsx2uzuw5azltl.dkim.amazonses.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"ou4uonrriluowzxzbk22en3exejgaa33._domainkey.outreach.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 1800,
            "ResourceRecords": [
                {"Value": "ou4uonrriluowzxzbk22en3exejgaa33.dkim.amazonses.com."},
            ],
        },
    },
    # 8. Microsoft 365 / GoDaddy Service CNAMEs
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"autodiscover.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "autodiscover.outlook.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"email.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "email.secureserver.net."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"lyncdiscover.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "webdir.online.lync.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"msoid.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "clientconfig.microsoftonline-p.net."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"pay.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "paylinks.commerce.godaddy.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"sip.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "sipdir.online.lync.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"www.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "getretirementtaxanalyzer.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"_domainconnect.{DOMAIN}",
            "Type": "CNAME",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "_domainconnect.gd.domaincontrol.com."},
            ],
        },
    },
    # 9. SRV records (Lync / Skype for Business)
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"_sip._tls.{DOMAIN}",
            "Type": "SRV",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "100 1 443 sipdir.online.lync.com."},
            ],
        },
    },
    {
        "Action": "UPSERT",
        "ResourceRecordSet": {
            "Name": f"_sipfederationtls._tcp.{DOMAIN}",
            "Type": "SRV",
            "TTL": 3600,
            "ResourceRecords": [
                {"Value": "100 1 5061 sipfed.online.lync.com."},
            ],
        },
    },
]


def main() -> None:
    session = get_boto3_session({}, profile_name=PROFILE)
    r53 = session.client("route53")

    logger.info("Applying %d resource record sets to Route 53 zone %s...", len(CHANGES), HOSTED_ZONE_ID)
    resp = r53.change_resource_record_sets(
        HostedZoneId=HOSTED_ZONE_ID,
        ChangeBatch={
            "Comment": "Initial import from GoDaddy zone file with M365 SPF authorization",
            "Changes": CHANGES,
        },
    )
    change_info = resp.get("ChangeInfo", {})
    logger.info("Change submitted: Id=%s Status=%s", change_info.get("Id"), change_info.get("Status"))

    # Print nameservers for user
    zone_info = r53.get_hosted_zone(Id=HOSTED_ZONE_ID)
    ns = zone_info.get("DelegationSet", {}).get("NameServers", [])
    print("\n" + "=" * 60)
    print("SUCCESS: Route 53 zone is fully configured!")
    print("GoDaddy Nameservers to set:")
    for server in ns:
        print(f"  - {server}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
