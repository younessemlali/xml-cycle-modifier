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
    """Mode commentaires"""
    st.header("💬 Mode Commentaires")
    st.write("Extraction des cycles depuis les commentaires XML (entre guillemets uniquement)")
    
    xml_file = st.file_uploader(
        "Choisissez votre fichier XML",
        type=['xml'],
        key="xml_comments_upload"
    )
    
    if xml_file is not None:
        # Lire XML
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
        
        if st.button("🔍 Analyser et traiter", key="process_comments"):
            count = 0
            modifications = []
            
            def replace_in_assignment(match):
                nonlocal count, modifications
                assignment = match.group(0)
                
                # Chercher cycle entre guillemets dans les commentaires
                comments = re.findall(r'<Comment>([^<]*)</Comment>', assignment)
                cycle_found = None
                
                for comment in comments:
                    # SEULEMENT chercher entre guillemets doubles
                    quotes = re.findall(r'"([^"]+)"', comment)
                    if quotes:
                        cycle_found = quotes[0].strip()
                        break
                
                # SEULEMENT modifier si un cycle a été trouvé entre guillemets
                if cycle_found:
                    new_assignment = re.sub(
                        r'(<IdValue[^>]*name=")MODELE("[^>]*>)[^<]*(</IdValue>)',
                        f'\\1CYCLE\\2{cycle_found}\\3',
                        assignment
                    )
                    if new_assignment != assignment:
                        count += 1
                        modifications.append(f"MODELE → CYCLE avec valeur: '{cycle_found}'")
                    return new_assignment
                else:
                    return assignment
            
            # Traiter tous les assignments
            modified_xml = re.sub(
                r'<Assignment[^>]*>[\s\S]*?</Assignment>',
                replace_in_assignment,
                xml_content
            )
            
            if count > 0:
                st.success(f"✅ {count} modifications effectuées!")
                st.info("💡 Seuls les assignments avec guillemets ont été modifiés")
                
                # Afficher les modifications
                with st.expander("Voir les modifications effectuées"):
                    for mod in modifications:
                        st.write(f"• {mod}")
                
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
                st.warning("⚠️ Aucune modification effectuée. Aucun cycle trouvé entre guillemets dans les commentaires.")

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
        count = xml_content.count('MODELE')
        st.info(f"📊 {count} occurrences de 'MODELE' trouvées")
        
        if st.button("🔄 Remplacer tout", key="process_brutal") and count > 0:
            # Remplacer
            modified_xml = xml_content.replace('MODELE', 'CYCLE')
            
            # Forcer la valeur par défaut
            modified_xml = re.sub(
                r'(<IdValue[^>]*name="CYCLE"[^>]*>)[^<]*(</IdValue>)',
                f'\\1{default_value}\\2',
                modified_xml
            )
            
            st.success(f"✅ {count} remplacements effectués avec '{default_value}'!")
            
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
    
    **Mode Commentaires**: Extrait les cycles depuis les commentaires XML (entre guillemets)
    
    **Mode Brutal**: Force tous les MODELE → CYCLE avec une valeur unique
    """)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Formats supportés")
    st.sidebar.markdown("""
    - **Encodages**: UTF-8, ISO-8859-1, CP1252
    - **CSV**: Séparateur `;`
    - **XML**: Tous formats standard
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
