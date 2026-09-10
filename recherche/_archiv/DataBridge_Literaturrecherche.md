---
title: "Literaturrecherche: Ontologien, Wissensrepräsentation & Wissensnetze"
subtitle: "Projekt DataBridge (26ss_CB_DataBridge) — Hochschule Karlsruhe / Universität Oviedo"
author: "Recherche-Zusammenstellung"
date: "Stand: Juli 2026"
lang: de
---

## Einordnung

Diese Zusammenstellung dient als erste Wissensbasis für die Literatur- und Grundlagenrecherche im Rahmen des F&E-Projekts **DataBridge**. Ziel des Projekts ist die Konzeption einer universell einsetzbaren Schnittstellenlösung zur automatisierten Datenakquise aus öffentlichen Repositorien, mit dem Anwendungsfall Onkologie/Genetik (Kooperation mit der Universität Oviedo) und besonderem Fokus auf Flexibilität gegenüber sich entwickelnden Datenstrukturen und Begriffsbeziehungen (Ontologien).

Das Dokument gliedert sich in zwei Teile: (1) eine Sammlung von Themen und Suchbegriffen zu Ontologien und Wissensrepräsentation, und (2) eine vertiefte Betrachtung von Formaten und Sprachen für Wissensnetze inklusive Vergleichsgrafiken.

---

## Teil 1 — Ontologien & Wissensrepräsentation: Themen und Suchbegriffe

### 1.1 Theoretische Grundlagen
- Ontologie (Informatik) vs. Taxonomie vs. Vokabular vs. Thesaurus — begriffliche Abgrenzung
- Description Logics (DL)
- Knowledge Representation and Reasoning (KRR)
- TBox / ABox (Schema- vs. Instanzebene)
- Upper Ontology / Top-Level Ontology (z. B. BFO — Basic Formal Ontology)

### 1.2 Semantic-Web-Standards
- RDF (Resource Description Framework) / RDFS
- OWL (Web Ontology Language) — OWL 2 Profile (EL, QL, RL)
- SKOS (Simple Knowledge Organization System)
- SPARQL (Abfragesprache für RDF)
- JSON-LD, Turtle (Serialisierungsformate)
- Knowledge Graph / Triple Store

### 1.3 Bio-/medizinische Ontologien (Bezug zum Oncology/Genetics-Anwendungsfall)
- **OBO Foundry** (Open Biological and Biomedical Ontologies) — Dachprojekt, aktuell über 100 registrierte Ontologien
- Gene Ontology (GO)
- Sequence Ontology (SO)
- Human Phenotype Ontology (HPO)
- Disease Ontology (DO)
- NCI Thesaurus (NCIt) — speziell Onkologie
- ICD-O (International Classification of Diseases for Oncology)
- SNOMED CT
- ChEBI (Chemical Entities of Biological Interest)
- Uberon (Anatomie, artübergreifend)

### 1.4 Ontology-based Data Integration (OBDA) — Architekturmuster
- Mediator-Wrapper-Architektur
- Global-as-View vs. Local-as-View
- Ontology-driven ETL / Semantic ETL
- KaBOB (Knowledge Base Of Biomedicine) als Referenzbeispiel für ontologiebasierte Integration von über 18 biomedizinischen Datenbanken

### 1.5 Umgang mit sich entwickelnden Strukturen (Flexibilitätsschwerpunkt des Projekts)
- Ontology Matching / Ontology Alignment
- Ontology Evolution / Versioning
- Schema Mapping / Semantic Mapping
- Ontology Merging

### 1.6 Terminology Services / Lookup-Dienste
- BioPortal (NCBO)
- EBI Ontology Lookup Service (OLS)
- Protégé (De-facto-Standard-Editor für Ontologien)

### 1.7 Relevante öffentliche Repositorien (Validierungsfall Onkologie/Genetik)
- NCBI (GenBank, PubMed, dbSNP)
- Ensembl
- GDC — Genomic Data Commons
- TCGA — The Cancer Genome Atlas
- cBioPortal
- GEO — Gene Expression Omnibus
- Programmatischer Zugriff: REST-APIs, GA4GH-Standards

### 1.8 Übergreifendes Prinzip
- **FAIR Data Principles** (Findable, Accessible, Interoperable, Reusable) — zentraler Bezugsrahmen für automatisierte Datenakquise in diesem Feld

### 1.9 Vorschläge für die Datenbank-Suche
`"ontology-based data integration" genomics` · `"semantic data integration" biomedical` · `OBO Foundry oncology` · `FAIR data ontology genomics` · `ontology alignment evolving schema`

---

## Teil 2 — Wissensnetze: Formate & Sprachen im Vergleich

### 2.1 Zwei grundlegende Datenmodelle

Wissensnetze (Knowledge Graphs) basieren im Kern auf zwei unterschiedlichen Modellierungsansätzen:

**RDF (Resource Description Framework, W3C-Standard).** Alles wird als Tripel dargestellt: Subjekt – Prädikat – Objekt (z. B. *Gen X – kodiert_für – Protein Y*). RDF bildet den Unterbau des gesamten Semantic-Web-Stacks, auf dem RDFS, OWL und SPARQL aufsetzen.

**Labeled Property Graph — LPG (z. B. Neo4j, TigerGraph).** Knoten und Kanten können direkt Eigenschaften (Properties) tragen. Informationen lassen sich damit unmittelbar an eine Kante/Relation binden, während dies bei RDF nur indirekt über Reifikation, RDF-star oder benannte Graphen möglich ist.

Diese Unterscheidung ist für DataBridge relevant, weil sie bestimmt, wie Datenherkunft, Konfidenzwerte oder Versionsinformationen zu einzelnen Beziehungen (z. B. „Mutation X assoziiert mit Krebsart Y — Quelle: Studie Z") abgebildet werden können.

![Vergleich RDF/OWL-Stack und Property-Graph-Modell](images/diagram_stack.png)

*Abbildung 1: Gegenüberstellung des RDF/OWL-Stacks (Semantic Web) und des Property-Graph-Modells. Der RDF/OWL-Stack bietet standardisierte formale Semantik (W3C), während für Property Graphs bislang kein vergleichbarer Standard für Schema und Reasoning existiert — Brückenansätze wie OWLStar oder PGO sind experimentell.*

### 2.2 Sprachen im RDF-Stack

| Ebene | Sprache/Format | Zweck |
|---|---|---|
| Schema (leichtgewichtig) | **RDFS** | einfache Klassen-/Eigenschaftshierarchien |
| Ontologie (formal) | **OWL** (OWL 2) | Klassenlogik, Axiome, automatisches Reasoning, basiert auf Description Logics |
| Kontrolliertes Vokabular | **SKOS** | Taxonomien/Thesauri ohne volle OWL-Logik |
| Abfragesprache | **SPARQL** | W3C-Standard zur Graph-Abfrage |

### 2.3 RDF-Serialisierungsformate

Serialisierungsformate legen fest, *wie* RDF-Tripel als Datei geschrieben werden — sie sind logisch identisch und verlustfrei ineinander konvertierbar, unterscheiden sich aber in Lesbarkeit, Kompaktheit und Verarbeitungsgeschwindigkeit.

![RDF-Serialisierungsformate im Überblick](images/diagram_serialization.png)

*Abbildung 2: RDF/XML war das ursprüngliche Standardformat, gilt aber als verbose und schwer lesbar. Turtle und N-Triples wurden für bessere menschliche Lesbarkeit bzw. Parsing-Performance entwickelt; JSON-LD verbindet RDF mit dem in Web-APIs gebräuchlichen JSON-Format.*

### 2.4 Property-Graph-Anfragesprachen

Die Sprachlandschaft auf der Property-Graph-Seite war lange fragmentierter als bei RDF:

- **Cypher** (Neo4j) — deklarativ, SQL-ähnlich, faktischer Industriestandard
- **Gremlin** (Apache TinkerPop) — prozedural, erlaubt Traversierung mit Schleifen/Verzweigungen
- **GQL** — seit April 2024 offizieller ISO/IEC-Standard (ISO/IEC 39075:2024) für Property-Graph-Datenbanken; die erste neue Datenbanksprachen-Norm der ISO seit SQL 1987. GQL ist in weiten Teilen mit Cypher kompatibel, was den Umstieg für bestehende Systeme erleichtert.

### 2.5 Vergleichstabelle RDF/OWL vs. Property Graph

| Kriterium | RDF/OWL | Labeled Property Graph |
|---|---|---|
| Abfragesprache | SPARQL (W3C-Empfehlung) | Cypher, Gremlin, GQL (ISO seit 2024) |
| Formale Semantik/Reasoning | OWL (Description Logics), aber oft verbose bei Abbildung auf RDF | kein einheitlicher Standard; Mapping-Vorschläge wie OWLStar existieren, sind aber nicht standardisiert |
| Informationen direkt an Kanten | nur indirekt (Reifikation, RDF-star, benannte Graphen) | direkt möglich (Properties an Kanten) |
| Unterscheidung Einzelaussage/Allaussage | formal unterscheidbar (TBox/ABox) | keine formale Unterscheidung |
| Stärke | semantische Präzision, Interoperabilität zwischen Systemen | Performance, intuitive Modellierung, große Analytics-Workloads |
| Typischer Einsatzbereich | Linked Open Data, Ontologie-Integration, Cross-System-Metadaten | Empfehlungssysteme, Betrugserkennung, große vernetzte Transaktionsdaten |

### 2.6 Zentrale Herausforderungen

1. **Formale Semantik vs. Standardisierung.** OWL besitzt über die Abbildung auf RDF eine W3C-normierte formale Semantik; für Property Graphs fehlt ein vergleichbarer Standard bislang vollständig.
2. **Ausdruckskraft vs. Praktikabilität.** Property Graphs sind kognitiv leicht verständlich, können aber z. B. nicht formal zwischen einer Einzelaussage („dieses Protein hat Eigenschaft X") und einer Allaussage („alle Proteine dieser Klasse haben Eigenschaft X") unterscheiden — OWL kann dies, wird dabei aber schnell komplex und für Menschen schwerer lesbar.
3. **Interoperabilität zwischen den Modellen.** Beide Modelle sind strukturell Graphen, doch verlustfreie automatische Transformation zwischen RDF und Property Graphs ist ein offenes, aktives Forschungsfeld (z. B. PGO-Ontologie als Brücke).
4. **Performance vs. Reasoning.** Property Graphs sind auf schnelle Traversierung optimiert (relevant für große, sich häufig ändernde Datenmengen), RDF/OWL auf semantische Präzision — komplexe OWL-DL-Reasoning-Operationen können bei großen Ontologien jedoch rechenintensiv werden (Decidability-Grenzen ausdrucksstarker Profile).

Für DataBridge stellt sich damit die Grundsatzfrage, ob die Flexibilitätsanforderung (sich entwickelnde Datenstrukturen/Ontologien) eher für einen RDF/OWL-Ansatz (klare Versionierung, formale Ontologie-Alignments) oder einen Property-Graph-Ansatz (schnelle strukturelle Anpassung ohne strikte Schemabindung) spricht — ggf. auch ein hybrides Modell.

---

## Offene Punkte für die weitere Recherche

- Vertiefung: Wie bilden konkrete Bio-Ontologien (z. B. OBO-Format vs. OWL) diese Formate praktisch ab?
- Architekturvergleich: Welches Modell (RDF/OWL vs. Property Graph) passt besser zum DataBridge-Anwendungsfall mit sich entwickelnden Datenstrukturen?
- Konkrete Tools/Frameworks je Sprache (z. B. RDFLib, Apache Jena, OWL API, Neo4j-Treiber) im Hinblick auf die spätere Implementierungsphase

## Quellen und weiterführende Literatur

*Diese Liste dient als Ausgangspunkt für die vertiefte Literaturrecherche; Originalquellen sollten für Zitate im Projektbericht direkt konsultiert werden.*

- Jackson, R. et al. (2021): *OBO Foundry in 2021: operationalizing open data principles to evaluate ontologies.* Database, Vol. 2021, baab069.
- Livingston, K. M. et al. (2015): *KaBOB: ontology-based semantic integration of biomedical databases.* BMC Bioinformatics.
- Waagmeester, A. et al.: *Semantic Units: Organizing knowledge graphs into semantically meaningful units of representation* (arXiv:2301.01227) — Vergleichstabelle RDF/OWL vs. Property Graph.
- *Rethinking OWL Expressivity: Semantic Units for FAIR and Cognitively Interoperable Knowledge Graphs* (arXiv:2407.10720)
- OBO Foundry — offizielle Projektseite: obofoundry.org
- W3C: RDF 1.1 Concepts and Abstract Syntax; RDF 1.1 Turtle; JSON-LD 1.1 (W3C-Empfehlungen)
- ISO/IEC 39075:2024 — *Information technology — Database languages — GQL*
- Wikipedia: *Graph Query Language* — Übersicht zur Entstehung und Einordnung von GQL
- PuppyGraph / TigerGraph Engineering-Blogs — praxisnahe Gegenüberstellungen RDF vs. Property Graph (Stand 2026)

---

*Zusammengestellt als Recherchegrundlage — die inhaltliche Prüfung und Vertiefung anhand der Originalquellen bleibt Teil der eigenständigen Literaturarbeit.*
