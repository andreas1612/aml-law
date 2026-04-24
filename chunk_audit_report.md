# Tailored Per-Schema Chunking Audit Report

This document proves that the AI now respects the unique schema of every JSON file (Parts vs Forms vs Indicator Arrays) rather than blindly guessing.

## appendix_1.json
* **Total Isolated Legal Nodes Processed**: 4
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `appendix_1.json.sections.informers_details`
**Architecture Applied:** Tailored: Form Template Translation (Fields grouped into single string)

**Raw Translated Text Length:** 89 characters

**Resulting Processed Chunks:**
> **Chunk 1** (89 chars): Form Section: 'INFORMER’S DETAILS'. Required fields: Name, Tel, Department, Fax, Position 

---

## appendix_2.json
* **Total Isolated Legal Nodes Processed**: 4
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `appendix_2.json.sections.header_details`
**Architecture Applied:** Tailored: Form Template Translation (Fields grouped into single string)

**Raw Translated Text Length:** 100 characters

**Resulting Processed Chunks:**
> **Chunk 1** (100 chars): Form Section: 'REPORT DETAILS'. Required fields: Reference, Customer’s Details, Informer, Department 

---

## appendix_3.json
* **Total Isolated Legal Nodes Processed**: 32
* **Nodes Requiring Fragmentation Cut**: 3

### Sample Tailored Extraction Check: `appendix_3.json.sections.terrorist_financing.indicators.0`
**Architecture Applied:** Tailored: Indicator Array Unpacking + Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 686 characters

**Resulting Processed Chunks:**
> **Chunk 1** (686 chars): 1. Sources and methods: The funding of terrorist organisations is made from both legal and illegal revenue generating activities. Criminal activities generating such proceeds include kidnappings (requiring ransom), extortion (demanding “protection” money), smuggling, thefts, robbery and narcotics trafficking. Legal fund raising methods used by terrorist groups include: i. collection of membership dues and/or subscriptions, ii. sale of books and other publications, iii. cultural and social events, iv. donations, v. community solicitations and fund raising appeals. Funds obtained from illegal sources are laundered by terrorist groups by the same methods used by criminal groups... 

> **Chunk 2** (499 chars): 1.Sources and methods: The funding of terrorist organisations is made from both legal and illegal revenue generating activities.Criminal activities generating such proceeds include kidnappings (requiring ransom), extortion (demanding “protection” money), smuggling, thefts, robbery and narcotics trafficking.Legal fund raising methods used by terrorist groups include: i.collection of membership dues and/or subscriptions, ii.sale of books and other publications, iii.cultural and social events, iv. 

> **Chunk 3** (178 chars): donations, v.community solicitations and fund raising appeals.Funds obtained from illegal sources are laundered by terrorist groups by the same methods used by criminal groups... 

---

## appendix_4.json
* **Total Isolated Legal Nodes Processed**: 14
* **Nodes Requiring Fragmentation Cut**: 1

### Sample Tailored Extraction Check: `appendix_4.json.paragraphs.3.points.iii`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 530 characters

**Resulting Processed Chunks:**
> **Chunk 1** (404 chars): If the opening of the account has been recommended by a third person as defined in paragraph 25, at least once every year, the third person who has introduced the customer provides a written confirmation that the capital base and the shareholding structure of the company or that of its holding company (if any) has not been altered by the issue of new bearer shares or the cancellation of existing ones. 

> **Chunk 2** (125 chars): If the account has been opened directly by the company, then the written confirmation is provided by the company’s directors. 

---

## appendix_5.json
* **Total Isolated Legal Nodes Processed**: 30
* **Nodes Requiring Fragmentation Cut**: 3

### Sample Tailored Extraction Check: `appendix_5.json.paragraphs.2.points.c`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 775 characters

**Resulting Processed Chunks:**
> **Chunk 1** (246 chars): In addition to the aim of preventing money laundering and terrorist financing, the abovementioned information is also essential for implementing the financial sanctions imposed against various persons by the United Nations and the European Union. 

> **Chunk 2** (528 chars): In this regard, identification document’s number, issuing date and country as well as the customer’s date of birth always appear on the copies of documents obtained, so that the Obliged Entity would be in a position to verify precisely whether a customer is included in the relevant list of persons subject to financial sanctions which are issued by the United Nations or the European Union based on a United Nations Security Council’s Resolution and Regulation or a Common Position of the European Union’s Council respectively. 

---

## part_1.json
* **Total Isolated Legal Nodes Processed**: 4
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `part_1.json.PART_I.paragraphs.1`
**Architecture Applied:** Standard Paragraph (No Fragmentation Needed)

**Raw Translated Text Length:** 125 characters

**Resulting Processed Chunks:**
> **Chunk 1** (125 chars): This Directive will be cited as the Directive for the Prevention and Suppression of Money Laundering and Terrorist Financing. 

---

## part_10.json
* **Total Isolated Legal Nodes Processed**: 3
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `part_10.json.PART_X.paragraphs.37`
**Architecture Applied:** Standard Paragraph (No Fragmentation Needed)

**Raw Translated Text Length:** 218 characters

**Resulting Processed Chunks:**
> **Chunk 1** (215 chars): The Directive DI144-2007-08 of 2012 for the prevention of money laundering and terrorist financing R.A.D.480/2012, the amending Directive R.A.D.192/2016 and the amending Directive R.A.D.262/2016 are hereby repealed. 

---

## part_2.json
* **Total Isolated Legal Nodes Processed**: 18
* **Nodes Requiring Fragmentation Cut**: 2

### Sample Tailored Extraction Check: `part_2.json.PART_II.paragraphs.5A`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 602 characters

**Resulting Processed Chunks:**
> **Chunk 1** (450 chars): Without prejudice to the provisions of section 58D of the Law, the designated member of the board of directors, that is referred to in the said section, may either be an executive or a non executive member.The Obliged Entity’s board of directors determines the policies and procedures to ensure the application of the provisions of section 58D of the Law, that are stated in the risk management and procedures manual referred to in paragraph 9(1)(c). 

> **Chunk 2** (150 chars): The said person may perform additional duties, where appropriate, taking into account the nature and the size of the activities of the Obliged Entity. 

---

## part_3.json
* **Total Isolated Legal Nodes Processed**: 46
* **Nodes Requiring Fragmentation Cut**: 4

### Sample Tailored Extraction Check: `part_3.json.PART_III.paragraphs.8.subparagraphs.2`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 570 characters

**Resulting Processed Chunks:**
> **Chunk 1** (403 chars): The Obliged Entity should appoint an alternate compliance officer, in case the compliance officer is absent, who should replace him temporarily, perform his duties as defined in the present Directive and the Law and fulfil the conditions of appointing a compliance officer.The Obliged Entity may outsource, as well, the function of the alternate compliance officer only if a natural person is appointed. 

> **Chunk 2** (165 chars): The Obliged Entity records in the risk management and procedures manual referred to in paragraph 9(1)(c) the procedures it intends to apply for the said appointment. 

---

## part_4.json
* **Total Isolated Legal Nodes Processed**: 58
* **Nodes Requiring Fragmentation Cut**: 1

### Sample Tailored Extraction Check: `part_4.json.PART_IV.paragraphs.16`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 615 characters

**Resulting Processed Chunks:**
> **Chunk 1** (368 chars): Risk management is a continuous process, carried out on a dynamic basis.Risk assessment is not an isolated event of a limited duration.Customers’ activities change as well as the services and financial instruments provided by the Obliged Entity change.The same happens to the financial instruments and the transactions used for money laundering or terrorist financing. 

> **Chunk 2** (243 chars): The measures, the procedures and controls are kept under regular review so that risks resulting from changes in the characteristics of existing customers, new customers, services and financial instruments are managed and countered effectively. 

---

## part_5.json
* **Total Isolated Legal Nodes Processed**: 41
* **Nodes Requiring Fragmentation Cut**: 9

### Sample Tailored Extraction Check: `part_5.json.PART_V.paragraphs.18.subparagraphs.1`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 839 characters

**Resulting Processed Chunks:**
> **Chunk 1** (338 chars): In addition to the provisions of sections 60, 61 and 62 of the Law that refer to the obligation for customer identification and due diligence procedures, the Obliged Entity ensure that the customer identification records remain completely updated with all relevant identification data and information throughout the business relationship. 

> **Chunk 2** (498 chars): The Obliged Entity examines and checks, on a regular basis, the validity and adequacy of the customer identification data and information it maintains, especially those concerning high risk customers.The procedures and controls of paragraph 9(1)(a) also determine the timeframe during which the regular review, examination and update of the customer identification is conducted.The outcome of the said review is recorded in a separate note/form which should be kept in the respective customer file. 

---

## part_6.json
* **Total Isolated Legal Nodes Processed**: 14
* **Nodes Requiring Fragmentation Cut**: 3

### Sample Tailored Extraction Check: `part_6.json.PART_VI.paragraphs.28.subparagraphs.1`
**Architecture Applied:** Standard Paragraph (Split by sentences)

**Raw Translated Text Length:** 670 characters

**Resulting Processed Chunks:**
> **Chunk 1** (454 chars): The definition of a suspicious transaction as well as the types of suspicious transactions which may be used for money laundering and terrorist financing are almost unlimited.A suspicious transaction will often be one which is inconsistent with a customer's known, legitimate business or personal activities or with the normal business of the specific account, or in general with the economic profile that the Obliged Entity has created for the customer. 

> **Chunk 2** (214 chars): The Obliged Entity ensures that maintains adequate information and knows enough about its customers' activities in order to recognise on time that a transaction or a series of transactions is unusual or suspicious. 

---

## part_7.json
* **Total Isolated Legal Nodes Processed**: 16
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `part_7.json.PART_VII.paragraphs.31.subparagraphs.1`
**Architecture Applied:** Standard Paragraph (No Fragmentation Needed)

**Raw Translated Text Length:** 230 characters

**Resulting Processed Chunks:**
> **Chunk 1** (230 chars): According to section 68(1) of the Law, the Obliged Entity keeps record of the documents/data mentioned in the above section of the Law and are specialised in the present Directive, including those referred to in paragraph 9(1)(k). 

---

## part_8.json
* **Total Isolated Legal Nodes Processed**: 7
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `part_8.json.PART_VIII.paragraphs.34.subparagraphs.1`
**Architecture Applied:** Standard Paragraph (No Fragmentation Needed)

**Raw Translated Text Length:** 154 characters

**Resulting Processed Chunks:**
> **Chunk 1** (154 chars): The Obliged Entity’s employees can be personally liable for failure to report information or suspicion, regarding money laundering or terrorist financing. 

---

## part_9.json
* **Total Isolated Legal Nodes Processed**: 3
* **Nodes Requiring Fragmentation Cut**: 0

### Sample Tailored Extraction Check: `part_9.json.PART_IX.paragraphs.36.subparagraphs.1`
**Architecture Applied:** Standard Paragraph (No Fragmentation Needed)

**Raw Translated Text Length:** 365 characters

**Resulting Processed Chunks:**
> **Chunk 1** (365 chars): The Obliged Entity designs and implements measures and procedures for the detection of actions that are in breach or may potentially be in breach of the provisions of the United Nations Security Council Resolutions or Decisions (‘Sanctions’) or/and the European Union Council Decisions and Regulations (‘Restrictive Measures’), as provided for in the Sanctions Law. 

---

