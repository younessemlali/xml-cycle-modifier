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
    
    # Dernier recours
    content = file_bytes.decode('utf-8', errors='replace')
    return content, 'utf-8-with-errors'

def extract_quoted_text(text):
    """
    Extrait le texte entre guillemets en supportant différents types de guillemets
    Retourne le premier texte trouvé entre guillemets ou None
    """
    # Patterns pour différents types de guillemets
    patterns = [
        r'"([^"]+)"',                    # Guillemets droits doubles
        r'"([^"]+)"',                    # Guillemets courbes ouvrants/fermants
        r'«([^»]+)»',                    # Guillemets français
        r"'([^']+)'",                    # Apostrophes simples
        r"'([^']+)'",                    # Apostrophes courbes
        r'„([^"]+)"',                    # Guillemets allemands
        r"‚([^']+)'",                    # Guillemets simples allemands
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            # Retourner le premier match trouvé, nettoyé
            return matches[0].strip()
    
    return None

def csv_mode():
    """Mode CSV avec mapping"""
    st.header("🗂️ Mode CSV")
    st.write("Upload d'un fichier CSV pour le mapping contrat → cycle")
    
    # Upload CSV
    csv_file = st.file_uploader(
        "Choisissez votre fichier CSV",
        type=['csv'],
        key="csv_upload",
        help="Format attendu: colonne 3 = contrat, colonne 7 = cycle (séparateur ;)"
    )
    
    if csv_file is not None:
        # Lire CSV
        csv_content, csv_encoding = detect_and_decode(csv_file.read())
        st.success(f"✅ CSV lu avec l'encodage: {csv_encoding}")
        
        # Parser CSV
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
            
            # Afficher un aperçu
            if mapping:
                st.write("**Aperçu du mapping:**")
                preview = dict(list(mapping.items())[:5])
                df_preview = pd.DataFrame(list(preview.items()), columns=['Contrat', 'Cycle'])
                st.dataframe(df_preview)
                if len(mapping) > 5:
                    st.write(f"... et {len(mapping) - 5} autres contrats")
        
        # Upload XML
        st.write("---")
        xml_file = st.file_uploader(
            "Choisissez votre fichier XML",
            type=['xml'],
            key="xml_csv_upload"
        )
        
        if xml_file is not None and mapping:
            # Lire XML
            xml_content, xml_encoding = detect_and_decode(xml_file.read())
            st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
            
            # Traitement
            if st.button("🔄 Traiter le fichier XML", key="process_csv"):
                count = 0
                processed_contracts = []
                
                for contrat, cycle in mapping.items():
                    if contrat in xml_content:
                        # Remplacer MODELE par CYCLE
                        xml_content = re.sub(
                            r'(<IdValue[^>]*name=")MODELE("[^>]*>)[^<]*(</IdValue>)',
                            f'\\1CYCLE\\2{cycle}\\3',
                            xml_content
                        )
                        count += 1
                        processed_contracts.append(f"{contrat} → {cycle}")
                
                if count > 0:
                    st.success(f"✅ {count} modifications effectuées!")
                    
                    # Afficher les modifications
                    with st.expander("Voir les modifications effectuées"):
                        for mod in processed_contracts:
                            st.write(f"• {mod}")
                    
                    # Téléchargement
                    timestamp = datetime.now().strftime('%H%M%S')
                    filename = f"{xml_file.name.split('.')[0]}_modified_{timestamp}.xml"
                    
                    # Encoder en ISO-8859-1 pour le téléchargement
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
                    st.warning("⚠️ Aucune modification effectuée. Vérifiez que les contrats du CSV correspondent à ceux du XML.")

def comments_mode():
    """Mode commentaires - Extraction depuis les balises StaffingShift"""
    st.header("💬 Mode Commentaires")
    st.write("Extraction des cycles depuis les commentaires dans les balises StaffingShift")
    st.info("🔍 Recherche la valeur entre guillemets dans `<Comment>` et met à jour `<IdValue name=\"MODELE\">` → `<IdValue name=\"CYCLE\">`")
    
    # Exemple pour l'utilisateur
    with st.expander("📖 Voir un exemple"):
        st.code("""
<StaffingShift shiftPeriod="weekly">
    <Id idOwner="EXT0">
        <IdValue name="MODELE">BH</IdValue>  <!-- Sera changé en: <IdValue name="CYCLE">GA - PROD</IdValue> -->
    </Id>
    <Name>Base horaire hebdomadaire</Name>
    <Hours>35.00</Hours>
    <StartTime>06:00:00</StartTime>
</StaffingShift>
<StaffingShift shiftPeriod="1">
    <Id idOwner="RIS">
        <IdValue>ST3</IdValue>
    </Id>
    <Name>JOURNEE / EQ JOUR / NUIT</Name>
    <Comment>6h à 13h40 dont 40min de pause non rémunérée "GA - PROD"</Comment>  <!-- Valeur extraite d'ici -->
</StaffingShift>
        """, language="xml")
    
    xml_file = st.file_uploader(
        "Choisissez votre fichier XML",
        type=['xml'],
        key="xml_comments_upload"
    )
    
    if xml_file is not None:
        # Lire XML
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
        
        # Options d'affichage
        show_preview = st.checkbox("Afficher un aperçu des commentaires trouvés", value=True)
        
        if st.button("🔍 Analyser et traiter", key="process_comments"):
            count = 0
            modifications = []
            comments_found = []
            
            # Pattern pour trouver les StaffingShift qui contiennent un Comment avec des guillemets
            pattern = r'<StaffingShift[^>]*>(?:(?!</StaffingShift>).)*<Comment>[^<]*"[^"]*"[^<]*</Comment>(?:(?!</StaffingShift>).)*</StaffingShift>'
            
            # Trouver tous les StaffingShift avec des commentaires contenant des guillemets
            shifts_with_comments = re.findall(pattern, xml_content, re.DOTALL)
            
            for shift in shifts_with_comments:
                # Extraire le commentaire
                comment_match = re.search(r'<Comment>([^<]*)</Comment>', shift)
                if comment_match:
                    comment_text = comment_match.group(1)
                    cycle_value = extract_quoted_text(comment_text)
                    
                    if cycle_value:
                        comments_found.append((comment_text, cycle_value))
            
            # Maintenant, pour chaque bloc qui contient MODELE, chercher la valeur du cycle suivant
            def replace_modele_in_block(match):
                nonlocal count, modifications
                block_content = match.group(0)
                
                # Chercher s'il y a un Comment avec des guillemets après ce bloc
                # On cherche dans un contexte plus large après ce StaffingShift
                block_start = match.start()
                search_area = xml_content[block_start:block_start + 2000]  # Chercher dans les 2000 caractères suivants
                
                # Chercher le prochain Comment avec guillemets
                comment_pattern = r'<Comment>([^<]*"[^"]*"[^<]*)</Comment>'
                comment_match = re.search(comment_pattern, search_area)
                
                if comment_match:
                    comment_text = comment_match.group(1)
                    cycle_value = extract_quoted_text(comment_text)
                    
                    if cycle_value:
                        # Remplacer MODELE par CYCLE et changer la valeur
                        new_block = re.sub(
                            r'(<IdValue\s+name=")MODELE(">)[^<]*(</IdValue>)',
                            f'\\1CYCLE\\2{cycle_value}\\3',
                            block_content
                        )
                        
                        if new_block != block_content:
                            count += 1
                            # Extraire l'ancienne valeur pour le rapport
                            old_value_match = re.search(r'<IdValue\s+name="MODELE">([^<]*)</IdValue>', block_content)
                            old_value = old_value_match.group(1) if old_value_match else "N/A"
                            modifications.append({
                                'old_value': old_value,
                                'new_value': cycle_value,
                                'comment': comment_text[:80] + '...' if len(comment_text) > 80 else comment_text
                            })
                        return new_block
                
                return block_content
            
            # Appliquer les remplacements
            # Pattern pour trouver les StaffingShift qui contiennent MODELE
            modele_pattern = r'<StaffingShift[^>]*>(?:(?!</StaffingShift>).)*<IdValue\s+name="MODELE">[^<]*</IdValue>(?:(?!</StaffingShift>).)*</StaffingShift>'
            
            modified_xml = re.sub(
                modele_pattern,
                replace_modele_in_block,
                xml_content,
                flags=re.DOTALL
            )
            
            # Afficher l'aperçu si demandé
            if show_preview and comments_found:
                st.write("### 📋 Commentaires avec valeurs entre guillemets trouvés")
                df_preview = pd.DataFrame(
                    comments_found[:10], 
                    columns=['Commentaire', 'Valeur extraite']
                )
                st.dataframe(df_preview, use_container_width=True)
                if len(comments_found) > 10:
                    st.caption(f"... et {len(comments_found) - 10} autres commentaires")
            
            if count > 0:
                st.success(f"✅ {count} modifications effectuées!")
                
                # Afficher les modifications détaillées
                with st.expander("📝 Détail des modifications"):
                    for i, mod in enumerate(modifications, 1):
                        st.write(f"**{i}.** `{mod['old_value']}` → `{mod['new_value']}`")
                        st.caption(f"   Depuis le commentaire: {mod['comment']}")
                
                # Statistiques
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Commentaires avec guillemets", len(comments_found))
                with col2:
                    st.metric("Modifications effectuées", count)
                
                # Téléchargement
                timestamp = datetime.now().strftime('%H%M%S')
                filename = f"{xml_file.name.split('.')[0]}_modified_{timestamp}.xml"
                
                # Encoder en ISO-8859-1 pour le téléchargement
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
            else:
                st.warning("⚠️ Aucune modification effectuée.")
                st.info("💡 Vérifiez que :")
                st.write("- Les commentaires contiennent des valeurs entre guillemets")
                st.write("- Il y a des balises `<IdValue name=\"MODELE\">` à modifier")
                st.write("- Les balises StaffingShift avec MODELE sont suivies par des StaffingShift avec des commentaires")
                
                # Montrer quelques exemples pour debug
                modele_count = len(re.findall(r'<IdValue\s+name="MODELE">', xml_content))
                st.write(f"\n🔍 Trouvé {modele_count} balises avec MODELE")
                st.write(f"🔍 Trouvé {len(comments_found)} commentaires avec des valeurs entre guillemets")

def brutal_mode():
    """Mode brutal"""
    st.header("⚡ Mode Brutal")
    st.write("Remplacement de tous les 'MODELE' par 'CYCLE' avec une valeur par défaut")
    
    # Valeur par défaut
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
        # Lire XML
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
        
        # Compter les occurrences
        count = len(re.findall(r'name=[\"\']?MODELE[\"\']?', xml_content, re.IGNORECASE))
        st.info(f"📊 {count} occurrences de 'MODELE' trouvées")
        
        if st.button("🔄 Remplacer tout", key="process_brutal") and count > 0:
            # Remplacer MODELE par CYCLE dans les attributs name
            modified_xml = re.sub(
                r'(name=[\"\']?)MODELE([\"\']?)',
                r'\1CYCLE\2',
                xml_content,
                flags=re.IGNORECASE
            )
            
            # Forcer la valeur par défaut pour tous les IdValue avec name="CYCLE"
            modified_xml = re.sub(
                r'(<IdValue[^>]*name=[\"\']?CYCLE[\"\']?[^>]*>)[^<]*(</IdValue>)',
                f'\\1{default_value}\\2',
                modified_xml,
                flags=re.IGNORECASE
            )
            
            st.success(f"✅ {count} remplacements effectués avec la valeur '{default_value}'!")
            
            # Téléchargement
            timestamp = datetime.now().strftime('%H%M%S')
            filename = f"{xml_file.name.split('.')[0]}_modified_{timestamp}.xml"
            
            # Encoder en ISO-8859-1 pour le téléchargement
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
    """Interface principale"""
    
    # Titre et description
    st.title("🔧 XML Cycle Modifier")
    st.write("Application web pour modifier les fichiers XML - Transformation MODELE → CYCLE")
    
    # Sidebar pour la navigation
    st.sidebar.title("Navigation")
    mode = st.sidebar.radio(
        "Choisissez votre mode:",
        ["Mode CSV", "Mode Commentaires", "Mode Brutal"],
        help="Sélectionnez la méthode de traitement selon vos données"
    )
    
    # Informations dans la sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ℹ️ Informations")
    st.sidebar.markdown("""
    **Mode CSV**: Utilise un fichier CSV pour mapper contrats → cycles
    
    **Mode Commentaires**: Extrait les cycles depuis les commentaires dans StaffingShift
    
    **Mode Brutal**: Force tous les MODELE → CYCLE avec une valeur unique
    """)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Formats supportés")
    st.sidebar.markdown("""
    - **Encodages**: UTF-8, ISO-8859-1, CP1252
    - **CSV**: Séparateur `;`
    - **XML**: Tous formats standard
    - **Guillemets**: " " « » ' ' " " „ " ‚ '
    """)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 Mode Commentaires")
    st.sidebar.markdown("""
    Cherche dans les balises `<Comment>` la valeur entre guillemets
    et met à jour les `<IdValue name="MODELE">` précédents
    """)
    
    # Affichage du mode sélectionné
    if mode == "Mode CSV":
        csv_mode()
    elif mode == "Mode Commentaires":
        comments_mode()
    elif mode == "Mode Brutal":
        brutal_mode()

if __name__ == "__main__":
    main()
