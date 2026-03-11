import streamlit as st
import re
import io
from datetime import datetime
import pandas as pd

# Configuration de la page
st.set_page_config(
    page_title="XML Cycle Modifier",
    page_icon="🔧",
    layout="wide"
)

def detect_and_decode(file_bytes):
    """Detecte l'encodage et decode le fichier"""
    encodings = ['utf-8', 'utf-8-sig', 'iso-8859-1', 'cp1252', 'latin1']
    for encoding in encodings:
        try:
            content = file_bytes.decode(encoding)
            return content, encoding
        except UnicodeDecodeError:
            continue
    content = file_bytes.decode('utf-8', errors='replace')
    return content, 'utf-8-with-errors'

def extract_quoted_text(text):
    patterns = [
        r'"([^"]+)"',
        r'\u201c([^\u201d]+)\u201d',
        r'\xab([^\xbb]+)\xbb',
        r"'([^']+)'",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[0].strip()
    return None

def build_cycle_modele_mapping(csv_bytes):
    """
    Construit le mapping cycle_code -> premier_code_modele depuis le CSV.
    Col[0] = TYPE INFO, col[2] = Code, col[7..] = 'CODE - NOM' des modèles associés.
    """
    content, _ = detect_and_decode(csv_bytes)
    lines = content.split('\n')
    mapping = {}
    for line in lines[1:]:
        if line.strip():
            cols = [c.strip().strip('"') for c in line.split(';')]
            if len(cols) >= 8 and cols[0] == 'Cycle de RA':
                cycle_code = cols[2]
                modeles_assoc = []
                for col in cols[7:]:
                    col = col.strip()
                    if col:
                        parts = col.split(' - ', 1)
                        modeles_assoc.append(parts[0].strip())
                if modeles_assoc:
                    # Le premier modèle de la liste = semaine 1
                    mapping[cycle_code] = modeles_assoc[0]
    return mapping

def add_modele_to_staffingshift(xml_content, cycle_modele_mapping):
    """
    Pour chaque bloc StaffingShift avec idOwner="EXT0" qui a un CYCLE mais pas de MODELE,
    ajoute <IdValue name="MODELE">CODE</IdValue> juste après l'IdValue CYCLE.
    """
    count = 0
    modifications = []

    def replace_shift(match):
        nonlocal count
        block = match.group(0)

        # Ne traiter que les blocs avec idOwner="EXT0"
        if 'idOwner="EXT0"' not in block:
            return block

        # Extraire la valeur du CYCLE
        cycle_match = re.search(r'<IdValue\s+name="CYCLE">([^<]+)</IdValue>', block)
        if not cycle_match:
            return block

        cycle_value = cycle_match.group(1).strip()

        # Vérifier si MODELE est déjà présent
        if re.search(r'<IdValue\s+name="MODELE">', block):
            return block

        # Trouver le code modèle correspondant
        modele_code = cycle_modele_mapping.get(cycle_value)
        if not modele_code:
            return block

        # Insérer <IdValue name="MODELE"> juste après la ligne CYCLE
        # Préserver l'indentation existante
        cycle_line_match = re.search(r'( *)(<IdValue\s+name="CYCLE">[^<]+</IdValue>)', block)
        if not cycle_line_match:
            return block

        indent = cycle_line_match.group(1)
        cycle_line = cycle_line_match.group(2)
        modele_line = f'{indent}<IdValue name="MODELE">{modele_code}</IdValue>'

        # Détecter le type de saut de ligne
        newline = '\r\n' if '\r\n' in block else '\n'

        new_block = block.replace(
            cycle_line,
            cycle_line + newline + modele_line,
            1
        )

        if new_block != block:
            count += 1
            modifications.append({
                'cycle': cycle_value,
                'modele': modele_code
            })
            return new_block

        return block

    pattern = r'<StaffingShift[^>]*>(?:(?!</StaffingShift>).)*</StaffingShift>'
    modified_xml = re.sub(pattern, replace_shift, xml_content, flags=re.DOTALL)

    return modified_xml, count, modifications


def csv_mode():
    """Mode CSV avec mapping"""
    st.header("🗂️ Mode CSV")
    st.write("Upload d'un fichier CSV pour le mapping contrat → cycle")

    csv_file = st.file_uploader(
        "Choisissez votre fichier CSV",
        type=['csv'],
        key="csv_upload",
        help="Format attendu: colonne 3 = contrat, colonne 7 = cycle (séparateur ;)"
    )

    if csv_file is not None:
        csv_content, csv_encoding = detect_and_decode(csv_file.read())
        st.success(f"✅ CSV lu avec l'encodage: {csv_encoding}")

        mapping = {}
        lines = csv_content.split('\n')

        if len(lines) > 1:
            for i, line in enumerate(lines[1:], 2):
                if line.strip():
                    cols = line.split(';')
                    if len(cols) >= 7:
                        contrat = cols[2].strip().strip('"')
                        cycle = cols[6].strip().strip('"')
                        if contrat and cycle:
                            mapping[contrat] = cycle

            st.info(f"📊 {len(mapping)} contrats chargés depuis le CSV")

            if mapping:
                st.write("**Aperçu du mapping:**")
                preview = dict(list(mapping.items())[:5])
                df_preview = pd.DataFrame(list(preview.items()), columns=['Contrat', 'Cycle'])
                st.dataframe(df_preview)
                if len(mapping) > 5:
                    st.write(f"... et {len(mapping) - 5} autres contrats")

        st.write("---")
        xml_file = st.file_uploader(
            "Choisissez votre fichier XML",
            type=['xml'],
            key="xml_csv_upload"
        )

        if xml_file is not None and mapping:
            xml_content, xml_encoding = detect_and_decode(xml_file.read())
            st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")

            if st.button("🔄 Traiter le fichier XML", key="process_csv"):
                count = 0
                processed_contracts = []

                for contrat, cycle in mapping.items():
                    if contrat in xml_content:
                        xml_content = re.sub(
                            r'(<IdValue[^>]*name=")MODELE("[^>]*>)[^<]*(</IdValue>)',
                            f'\\1CYCLE\\2{cycle}\\3',
                            xml_content
                        )
                        count += 1
                        processed_contracts.append(f"{contrat} → {cycle}")

                if count > 0:
                    st.success(f"✅ {count} modifications effectuées!")
                    with st.expander("Voir les modifications effectuées"):
                        for mod in processed_contracts:
                            st.write(f"• {mod}")

                    timestamp = datetime.now().strftime('%H%M%S')
                    filename = f"{xml_file.name.split('.')[0]}_modified_{timestamp}.xml"

                    try:
                        xml_bytes = xml_content.encode('iso-8859-1', errors='replace')
                    except:
                        xml_bytes = xml_content.encode('utf-8', errors='replace')

                    st.download_button(
                        label="📥 Télécharger le XML modifié",
                        data=xml_bytes,
                        file_name=filename,
                        mime="application/xml"
                    )
                else:
                    st.warning("⚠️ Aucune modification effectuée.")


def comments_mode():
    """Mode commentaires - Extraction depuis les balises StaffingShift"""
    st.header("💬 Mode Commentaires")
    st.write("Extraction des cycles depuis les commentaires dans les balises StaffingShift")
    st.info("🔍 Recherche la valeur entre guillemets dans `<Comment>` et met à jour `<IdValue name=\"MODELE\">` → `<IdValue name=\"CYCLE\">`, puis ajoute le MODELE RA correspondant.")

    with st.expander("📖 Voir un exemple — structure XML attendue en sortie"):
        st.code("""<StaffingShift shiftPeriod="weekly">
  <Id idOwner="EXT0">
    <IdValue name="CYCLE">BS-PROD GRENA</IdValue>
    <IdValue name="MODELE">30</IdValue>
  </Id>
  <Name>Base horaire hebdomadaire</Name>
  <Hours>35.00</Hours>
  <StartTime>06:00:00</StartTime>
</StaffingShift>""", language="xml")

    # Upload CSV pour mapping cycle->modèle
    st.markdown("#### 1️⃣ Fichier CSV INEOS (cycles & modèles RA)")
    csv_file = st.file_uploader(
        "Choisissez le fichier CSV edition_liasse",
        type=['csv'],
        key="csv_comments_upload",
        help="Fichier CSV contenant les colonnes Cycle de RA et Modèle de RA"
    )

    cycle_modele_mapping = {}
    if csv_file is not None:
        cycle_modele_mapping = build_cycle_modele_mapping(csv_file.read())
        st.success(f"✅ {len(cycle_modele_mapping)} correspondances cycle→modèle chargées")
        if cycle_modele_mapping:
            with st.expander("Voir le mapping cycle → modèle (semaine 1)"):
                df = pd.DataFrame(
                    list(cycle_modele_mapping.items()),
                    columns=['Cycle RA', 'Code Modèle RA (semaine 1)']
                )
                st.dataframe(df, use_container_width=True)

    st.markdown("#### 2️⃣ Fichier XML à corriger")
    xml_file = st.file_uploader(
        "Choisissez votre fichier XML",
        type=['xml'],
        key="xml_comments_upload"
    )

    if xml_file is not None:
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
        show_preview = st.checkbox("Afficher un aperçu des commentaires trouvés", value=True)

        if st.button("🔍 Analyser et traiter", key="process_comments"):
            count_cycle = 0
            modifications_cycle = []
            comments_found = []

            # --- Étape 1 : MODELE → CYCLE depuis les <Comment> ---
            pattern = r'<StaffingShift[^>]*>(?:(?!</StaffingShift>).)*<Comment>[^<]*"[^"]*"[^<]*</Comment>(?:(?!</StaffingShift>).)*</StaffingShift>'
            shifts_with_comments = re.findall(pattern, xml_content, re.DOTALL)

            for shift in shifts_with_comments:
                comment_match = re.search(r'<Comment>([^<]*)</Comment>', shift)
                if comment_match:
                    comment_text = comment_match.group(1)
                    cycle_value = extract_quoted_text(comment_text)
                    if cycle_value:
                        comments_found.append((comment_text, cycle_value))

            def replace_modele_in_block(match):
                nonlocal count_cycle, modifications_cycle
                block_content = match.group(0)
                block_start = match.start()
                search_area = xml_content[block_start:block_start + 2000]

                comment_pattern = r'<Comment>([^<]*"[^"]*"[^<]*)</Comment>'
                comment_match = re.search(comment_pattern, search_area)

                if comment_match:
                    comment_text = comment_match.group(1)
                    cycle_value = extract_quoted_text(comment_text)

                    if cycle_value:
                        new_block = re.sub(
                            r'(<IdValue\s+name=")MODELE(">)[^<]*(</IdValue>)',
                            f'\\1CYCLE\\2{cycle_value}\\3',
                            block_content
                        )

                        if new_block != block_content:
                            count_cycle += 1
                            old_value_match = re.search(r'<IdValue\s+name="MODELE">([^<]*)</IdValue>', block_content)
                            old_value = old_value_match.group(1) if old_value_match else "N/A"
                            modifications_cycle.append({
                                'old_value': old_value,
                                'new_value': cycle_value,
                                'comment': comment_text[:80] + '...' if len(comment_text) > 80 else comment_text
                            })
                        return new_block

                return block_content

            modele_pattern = r'<StaffingShift[^>]*>(?:(?!</StaffingShift>).)*<IdValue\s+name="MODELE">[^<]*</IdValue>(?:(?!</StaffingShift>).)*</StaffingShift>'
            xml_modified = re.sub(modele_pattern, replace_modele_in_block, xml_content, flags=re.DOTALL)

            # --- Étape 2 : Ajout de <IdValue name="MODELE"> via mapping CSV ---
            count_modele = 0
            modifications_modele = []
            if cycle_modele_mapping:
                xml_modified, count_modele, modifications_modele = add_modele_to_staffingshift(
                    xml_modified, cycle_modele_mapping
                )

            total_modifications = count_cycle + count_modele

            # Affichage résultats
            if show_preview and comments_found:
                st.write("### 📋 Commentaires avec valeurs entre guillemets trouvés")
                df_preview = pd.DataFrame(comments_found[:10], columns=['Commentaire', 'Valeur extraite'])
                st.dataframe(df_preview, use_container_width=True)
                if len(comments_found) > 10:
                    st.caption(f"... et {len(comments_found) - 10} autres commentaires")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("MODELE → CYCLE (depuis Comment)", count_cycle)
            with col2:
                st.metric("MODELE RA ajoutés (depuis CSV)", count_modele)
            with col3:
                st.metric("Total modifications", total_modifications)

            if count_cycle > 0:
                with st.expander("📝 Détail : MODELE → CYCLE"):
                    for i, mod in enumerate(modifications_cycle, 1):
                        st.write(f"**{i}.** `{mod['old_value']}` → `{mod['new_value']}`")
                        st.caption(f"   Depuis le commentaire: {mod['comment']}")

            if count_modele > 0:
                with st.expander("📝 Détail : MODELE RA ajoutés"):
                    for i, mod in enumerate(modifications_modele, 1):
                        st.write(f"**{i}.** Cycle `{mod['cycle']}` → Modèle `{mod['modele']}`")

            if total_modifications > 0:
                timestamp = datetime.now().strftime('%H%M%S')
                filename = f"{xml_file.name.split('.')[0]}_modified_{timestamp}.xml"

                try:
                    xml_bytes = xml_modified.encode('iso-8859-1', errors='replace')
                except:
                    xml_bytes = xml_modified.encode('utf-8', errors='replace')

                st.success(f"✅ {total_modifications} modifications effectuées!")
                st.download_button(
                    label="📥 Télécharger le XML modifié",
                    data=xml_bytes,
                    file_name=filename,
                    mime="application/xml"
                )
            else:
                st.warning("⚠️ Aucune modification effectuée.")
                modele_count = len(re.findall(r'<IdValue\s+name="MODELE">', xml_content))
                st.write(f"🔍 Balises MODELE trouvées: {modele_count}")
                st.write(f"🔍 Commentaires avec guillemets: {len(comments_found)}")
                if not cycle_modele_mapping:
                    st.info("💡 Uploadez le CSV INEOS pour ajouter automatiquement les codes MODELE RA.")


def brutal_mode():
    """Mode brutal"""
    st.header("⚡ Mode Brutal")
    st.write("Remplacement de tous les 'MODELE' par 'CYCLE' avec une valeur par défaut")

    default_value = st.text_input(
        "Valeur par défaut pour CYCLE:",
        value="GA - PROD",
        help="Cette valeur sera utilisée pour tous les remplacements"
    )

    xml_file = st.file_uploader(
        "Choisissez votre fichier XML",
        type=['xml'],
        key="xml_brutal_upload"
    )

    if xml_file is not None and default_value:
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")

        count = len(re.findall(r'name=[\"\'"]?MODELE[\"\'"]?', xml_content, re.IGNORECASE))
        st.info(f"📊 {count} occurrences de 'MODELE' trouvées")

        if st.button("🔄 Remplacer tout", key="process_brutal") and count > 0:
            modified_xml = re.sub(
                r'(name=[\"\'"]?)MODELE([\"\'"]?)',
                r'\1CYCLE\2',
                xml_content,
                flags=re.IGNORECASE
            )
            modified_xml = re.sub(
                r'(<IdValue[^>]*name=[\"\'"]?CYCLE[\"\'"]?[^>]*>)[^<]*(</IdValue>)',
                f'\\1{default_value}\\2',
                modified_xml,
                flags=re.IGNORECASE
            )

            st.success(f"✅ {count} remplacements effectués avec la valeur '{default_value}'!")

            timestamp = datetime.now().strftime('%H%M%S')
            filename = f"{xml_file.name.split('.')[0]}_modified_{timestamp}.xml"

            try:
                xml_bytes = modified_xml.encode('iso-8859-1', errors='replace')
            except:
                xml_bytes = modified_xml.encode('utf-8', errors='replace')

            st.download_button(
                label="📥 Télécharger le XML modifié",
                data=xml_bytes,
                file_name=filename,
                mime="application/xml"
            )


def main():
    st.title("🔧 XML Cycle Modifier")
    st.write("Application web pour modifier les fichiers XML - Transformation MODELE → CYCLE + ajout MODELE RA")

    st.sidebar.title("Navigation")
    mode = st.sidebar.radio(
        "Choisissez votre mode:",
        ["Mode CSV", "Mode Commentaires", "Mode Brutal"],
        help="Sélectionnez la méthode de traitement selon vos données"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ℹ️ Informations")
    st.sidebar.markdown("""
    **Mode CSV**: Mappe contrats → cycles via fichier CSV
    
    **Mode Commentaires**: Extrait les cycles depuis les `<Comment>`, puis ajoute le code MODELE RA depuis le CSV INEOS
    
    **Mode Brutal**: Force tous les MODELE → CYCLE avec une valeur unique
    """)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 Structure XML générée")
    st.sidebar.code("""<StaffingShift shiftPeriod="weekly">
  <Id idOwner="EXT0">
    <IdValue name="CYCLE">BS-PROD GRENA</IdValue>
    <IdValue name="MODELE">30</IdValue>
  </Id>
  ...
</StaffingShift>""", language="xml")

    if mode == "Mode CSV":
        csv_mode()
    elif mode == "Mode Commentaires":
        comments_mode()
    elif mode == "Mode Brutal":
        brutal_mode()


if __name__ == "__main__":
    main()
