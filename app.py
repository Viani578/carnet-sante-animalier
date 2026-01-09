from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak, HRFlowable, KeepTogether
from reportlab.lib.units import inch, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from PIL import Image as PILImage
import os
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import ObjectId
from datetime import datetime
import base64
import io
import tempfile
import random
import tempfile

# Charger variables .env
load_dotenv()

app = Flask(__name__)

# Configurations
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")

# Connexion MongoDB
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("DB_NAME")]

# Créer le dossier uploads
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Fonction utilitaire pour formater les dates
def format_date(date_str):
    """Formate une date de YYYY-MM-DD à DD/MM/YYYY"""
    if not date_str:
        return ""
    try:
        if "-" in date_str:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%d/%m/%Y")
        return date_str
    except:
        return date_str

# ==================== ROUTES PAGES D'ACCUEIL ET NAVIGATION ====================

@app.route("/nouveau-carnet")
def index():
    """Page pour créer un nouveau carnet"""
    return render_template("index.html")

@app.route("/identification")
def identification_carte():
    """Page pour créer un document d'identification"""
    return render_template("carte_identification.html")

# Route pour l'attestation vétérinaire
@app.route('/attestation')
def attestation():
    return render_template('attestation.html')

# Route pour servir le fichier attestation.html directement
@app.route('/attestation.html')
def attestation_file():
    return send_file('templates/attestation.html')

@app.route("/")
def home():
    """Page d'accueil avec toutes les fonctionnalités"""
    # Récupérer quelques statistiques
    carnets_count = db.carnets.count_documents({})
    
    # Vérifier si la collection factures existe
    if 'factures' in db.list_collection_names():
        factures_count = db.factures.count_documents({})
    else:
        factures_count = 0
    
    return render_template("home.html", 
                         carnets_count=carnets_count,
                         factures_count=factures_count)

@app.route("/dashboard")
@app.route("/accueil")
def dashboard():
    """Alias pour la page d'accueil"""
    return redirect(url_for("home"))

# ==================== ROUTE CARTE D'IDENTIFICATION ====================

@app.route("/carte-identification/generer", methods=["POST"])
def generer_carte_identification():
    """Génère la carte d'identification"""
    try:
        # Récupérer les données du formulaire
        data = {
            # Informations propriétaire
            "ownerName": request.form.get("ownerName", "").strip(),
            "ownerAddress": request.form.get("ownerAddress", "").strip(),
            "phone1": request.form.get("phone1", "").strip(),
            "phone2": request.form.get("phone2", "").strip(),
            "email": request.form.get("email", "").strip(),
            
            # Vétérinaire traitant
            "veterinaireNom": request.form.get("veterinaireNom", "").strip(),
            "veterinaireContact": request.form.get("veterinaireContact", "").strip(),
            
            # Identification
            "animalId": request.form.get("animalId", "").strip(),
            "password": request.form.get("password", "").strip(),
            "idDate": request.form.get("idDate", "").strip(),
            "idLocation": request.form.get("idLocation", "").strip(),
            
            # Animal
            "animalName": request.form.get("animalName", "").strip(),
            "animalEspece": request.form.get("animalEspece", "CHAT").strip(),
            "birthDate": request.form.get("birthDate", "").strip(),
            "breed": request.form.get("breed", "").strip(),
            "coat": request.form.get("coat", "").strip(),
            "hairType": request.form.get("hairType", "COURT").strip(),
            "sex": request.form.get("sex", "MALE").strip(),
            "sterilise": request.form.get("sterilise", "NON").strip(),
            "paysOrigine": request.form.get("paysOrigine", "FRANCE").strip(),
            
            # Métadonnées
            "date_creation": datetime.now(),
            "numero_carte": f"CART-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}",
        }
        
        # Sauvegarde dans MongoDB
        inserted = db.cartes_identification.insert_one(data)
        
        # Déterminer quelle partie générer
        partie = request.form.get("partie", "complete")
        
        if partie == "haute":
            pdf_path = generate_carte_identification_haute(data, str(inserted.inserted_id))
            nom_fichier = f"Carte_Identification_Haute_{data['animalName'].replace(' ', '_')}.pdf"
        elif partie == "basse":
            pdf_path = generate_carte_identification_basse(data, str(inserted.inserted_id))
            nom_fichier = f"Carte_Identification_Basse_{data['animalName'].replace(' ', '_')}.pdf"
        else:
            pdf_path = generate_carte_identification_complete(data, str(inserted.inserted_id))
            nom_fichier = f"Carte_Identification_Complete_{data['animalName'].replace(' ', '_')}.pdf"
        
        return send_file(pdf_path, as_attachment=True, download_name=nom_fichier)
        
    except Exception as e:
        print(f"Erreur génération carte identification: {e}")
        return f"Erreur lors de la génération: {str(e)}", 500

# ==================== ROUTE ATTESTATION VÉTÉRINAIRE ====================

@app.route("/attestation/generer", methods=["POST"])
def generer_attestation():
    """Génère l'attestation vétérinaire PDF"""
    try:
        # Récupérer les données du formulaire
        data = {
            # Informations vétérinaire
            "vet_fullname": request.form.get("vet-fullname", "").strip(),
            "vet_registration": request.form.get("vet-registration", "").strip(),
            "vet_address": request.form.get("vet-address", "").strip(),
            "vet_phone": request.form.get("vet-phone", "").strip(),
            "vet_email": request.form.get("vet-email", "").strip(),
            
            # Informations animal
            "animal_name": request.form.get("animal-name", "").strip(),
            "animal_species": request.form.get("animal-species", "").strip(),
            "animal_breed": request.form.get("animal-breed", "").strip(),
            "animal_gender": request.form.get("animal-gender", "").strip(),
            "animal_couleur": request.form.get("animal-couleur", "").strip(),
            "animal_puce": request.form.get("animal-puce", "").strip(),
            "animal_id": request.form.get("animal-id", "").strip(),
            
            # Informations propriétaire
            "owner_name": request.form.get("owner-name", "").strip(),
            "owner_address": "",  # Non présent dans le formulaire HTML
            "owner_phone": "",    # Non présent dans le formulaire HTML
            "owner_email": "",    # Non présent dans le formulaire HTML
            
            # Certifications
            "attestation_health": request.form.get("attestation-health") == "on",
            "attestation_vaccination": request.form.get("attestation-vaccination") == "on",
            "attestation_disease": request.form.get("attestation-disease") == "on",
            "attestation_transport": request.form.get("attestation-transport") == "on",
            
            # Dates et lieu
            "date": request.form.get("date", "").strip(),
            "city": request.form.get("city", "").strip(),
            "validity_date": "",  # Non présent dans le formulaire HTML
            
            # Observations
            "observations": "",  # Non présent dans le formulaire HTML
            
            # Numéro d'attestation
            "numero_attestation": f"ATT-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}",
            
            # Fichiers
            "stamp_image": None,
            "signature_path": None,
            
            "date_creation": datetime.now()
        }
        
        # Gestion de l'upload du cachet
        if 'stamp-file' in request.files and request.files['stamp-file'].filename != '':
            stamp_file = request.files['stamp-file']
            filename = secure_filename(f"cachet_attestation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            stamp_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            stamp_file.save(stamp_path)
            data["stamp_image"] = stamp_path
        
        # Gestion de la signature (maintenant dans les données du formulaire)
        if 'signature-data' in request.form and request.form['signature-data']:
            signature_data = request.form['signature-data']
            if signature_data.startswith('data:image'):
                try:
                    header, encoded = signature_data.split(",", 1)
                    signature_binary = base64.b64decode(encoded)
                    
                    filename = f"signature_attestation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    signature_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                    
                    with open(signature_path, 'wb') as f:
                        f.write(signature_binary)
                    data["signature_path"] = signature_path
                except Exception as e:
                    print(f"Erreur signature attestation: {e}")
        
        # Sauvegarde dans MongoDB (collection attestations)
        inserted = db.attestations.insert_one(data)
        
        # Générer le PDF de l'attestation
        pdf_path = generate_attestation_pdf(data, str(inserted.inserted_id))
        
        # Nom du fichier PDF
        nom_fichier = f"Attestation_Veterinaire_{data['animal_name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(pdf_path, as_attachment=True, download_name=nom_fichier)
        
    except Exception as e:
        print(f"Erreur génération attestation: {e}")
        return f"Erreur lors de la génération de l'attestation: {str(e)}", 500

# ==================== ROUTES CARNET DE SANTÉ ====================

@app.route("/save", methods=["POST"])
def save():
    try:
        # Récupération des données du formulaire
        data = {
            # Identité de l'animal
            "name": request.form.get("name", "").strip(),
            "species": request.form.get("species", "").strip(),
            "breed": request.form.get("breed", "").strip(),
            "age": request.form.get("age", "").strip(),
            "sex": request.form.get("sex", "").strip(),
            "sterilise": request.form.get("sterilise", "").strip(),
            "poids": request.form.get("poids", "").strip(),
            "identification": request.form.get("identification", "").strip(),
            
            # Santé
            "allergies": request.form.get("allergies", "").strip(),
            "antecedents": request.form.get("antecedents", "").strip(),
            "traitement": request.form.get("traitement", "").strip(),
            
            # Attestation
            "attestation_date": request.form.get("attestation_date", "").strip(),
            "attestation_veterinaire": request.form.get("attestation_veterinaire", "").strip(),
            "attestation_ordre": request.form.get("attestation_ordre", "").strip(),
            "attestation_validite": request.form.get("attestation_validite", "").strip(),
            "attestation_observations": request.form.get("attestation_observations", "").strip(),
            "signature_data": request.form.get("signature_data", "").strip(),
            
            # Propriétaire
            "proprietaire_nom": request.form.get("proprietaire_nom", "").strip(),
            "proprietaire_tel": request.form.get("proprietaire_tel", "").strip(),
            "proprietaire_email": request.form.get("proprietaire_email", "").strip(),
            "proprietaire_adresse": request.form.get("proprietaire_adresse", "").strip(),
            "proprietaire_ville": request.form.get("proprietaire_ville", "").strip(),
            "proprietaire_cp": request.form.get("proprietaire_cp", "").strip(),
            
            # Vétérinaire
            "veterinaire_cabinet": request.form.get("veterinaire_cabinet", "").strip(),
            "veterinaire_tel": request.form.get("veterinaire_tel", "").strip(),
            "veterinaire_adresse": request.form.get("veterinaire_adresse", "").strip(),
            "veterinaire_email": request.form.get("veterinaire_email", "").strip(),
            
            # Vaccinations (tableau dynamique)
            "vaccins": [],
            
            # Antiparasitaires (tableau dynamique)
            "antiparasitaires": [],
            
            # Fichiers
            "photo": None,
            "cachet": None,
            "signature": None,
            
            "date_creation": datetime.now()
        }
        
        # Récupération des vaccinations
        i = 0
        while f"vaccins[{i}][type]" in request.form:
            vaccin = {
                "type": request.form.get(f"vaccins[{i}][type]", "").strip(),
                "date": request.form.get(f"vaccins[{i}][date]", "").strip(),
                "rappel": request.form.get(f"vaccins[{i}][rappel]", "").strip(),
                "lot": request.form.get(f"vaccins[{i}][lot]", "").strip()
            }
            if vaccin["type"]:
                data["vaccins"].append(vaccin)
            i += 1
        
        # Récupération des antiparasitaires
        j = 0
        while f"antiparasitaires[{j}][type]" in request.form:
            antipara = {
                "type": request.form.get(f"antiparasitaires[{j}][type]", "").strip(),
                "date": request.form.get(f"antiparasitaires[{j}][date]", "").strip(),
                "produit": request.form.get(f"antiparasitaires[{j}][produit]", "").strip(),
                "prochaine_date": request.form.get(f"antiparasitaires[{j}][prochaine_date]", "").strip()
            }
            if antipara["type"]:
                data["antiparasitaires"].append(antipara)
            j += 1
        
        # Gestion de l'upload de la photo
        if 'photo' in request.files and request.files['photo'].filename != '':
            photo_file = request.files['photo']
            filename = secure_filename(f"photo_{data['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{photo_file.filename.split('.')[-1]}")
            photo_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            photo_file.save(photo_path)
            
            # Redimensionner la photo
            img = PILImage.open(photo_path)
            img.thumbnail((800, 800))
            img.save(photo_path)
            data["photo"] = photo_path
        
        # Gestion de l'upload du cachet
        if 'cachet' in request.files and request.files['cachet'].filename != '':
            cachet_file = request.files['cachet']
            filename = secure_filename(f"cachet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            cachet_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            cachet_file.save(cachet_path)
            data["cachet"] = cachet_path
        
        # Gestion de la signature
        if data["signature_data"] and data["signature_data"].startswith('data:image'):
            try:
                header, encoded = data["signature_data"].split(",", 1)
                signature_binary = base64.b64decode(encoded)
                
                filename = f"signature_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                signature_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                
                with open(signature_path, 'wb') as f:
                    f.write(signature_binary)
                data["signature"] = signature_path
            except Exception as e:
                print(f"Erreur signature: {e}")
        
        # Sauvegarde dans MongoDB
        inserted = db.carnets.insert_one(data)
        
        # Générer le PDF du CARNET DE SANTÉ
        pdf_path = generate_health_book_pdf(data, str(inserted.inserted_id))
        
        return send_file(pdf_path, as_attachment=True, 
                        download_name=f"Carnet_Sante_{data['name'].replace(' ', '_')}.pdf")
        
    except Exception as e:
        print(f"Erreur: {e}")
        return f"Erreur lors de la sauvegarde: {str(e)}", 500

@app.route("/carnets")
def liste_carnets():
    """Liste tous les carnets"""
    carnets = list(db.carnets.find().sort("date_creation", -1))
    return render_template("liste.html", carnets=carnets)

@app.route("/delete/<id>")
def delete_carnet(id):
    """Supprimer un carnet"""
    db.carnets.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("liste_carnets"))

# ==================== ROUTES FACTURES ====================

@app.route("/facture/nouvelle")
def nouvelle_facture():
    """Page pour créer une nouvelle facture"""
    carnets = list(db.carnets.find().sort("date_creation", -1))
    return render_template("facture_form.html", carnets=carnets, carnet=None, 
                          carnet_id=None, today=datetime.now().strftime('%Y-%m-%d'))

@app.route("/facture/<carnet_id>")
def facture_par_carnet(carnet_id):
    """Page de facture pour un carnet spécifique"""
    try:
        carnet = db.carnets.find_one({"_id": ObjectId(carnet_id)})
        if carnet:
            return render_template("facture_form.html", carnet=carnet, 
                                 carnet_id=carnet_id, today=datetime.now().strftime('%Y-%m-%d'))
        else:
            return redirect(url_for("nouvelle_facture"))
    except:
        return redirect(url_for("nouvelle_facture"))

@app.route("/facture/generer", methods=["POST"])
def generer_facture():
    """Génère la facture PDF"""
    try:
        # Récupérer les données du formulaire
        facture_data = {
            "carnet_id": request.form.get("carnet_id"),
            "entreprise": {
                "nom": request.form.get("entreprise_nom", ""),
                "siret": request.form.get("siret", ""),
                "tva": request.form.get("tva", ""),
                "adresse": request.form.get("entreprise_adresse", ""),
                "cp": request.form.get("entreprise_cp", ""),
                "ville": request.form.get("entreprise_ville", ""),
                "cp1": request.form.get("entreprise_cp1", ""),
                "ville1": request.form.get("entreprise_ville1", ""),
                "cp2": request.form.get("entreprise_cp2", ""),
                "ville2": request.form.get("entreprise_ville2", ""),
                "tel": request.form.get("entreprise_tel", ""),
                "email": request.form.get("entreprise_email", "")
            },
            "client": {
                "nom": request.form.get("client_nom", ""),
                "tel": request.form.get("client_tel", ""),
                "email": request.form.get("client_email", ""),
                "adresse": request.form.get("client_adresse", ""),
                "cp": request.form.get("client_cp", ""),
                "ville": request.form.get("client_ville", "")
            },
            "livraison": {
                "date": request.form.get("date_livraison", ""),
                "heure_prise": request.form.get("heure_prise", ""),
                "heure_livraison": request.form.get("heure_livraison", ""),
                "espece": request.form.get("espece_animal", ""),
                "race": request.form.get("race_animal", ""),
                "notes": request.form.get("notes", "")
            },
            "paiement": {
                "conditions": request.form.get("conditions_paiement", ""),
                "mentions": request.form.get("mentions", "")
            },
            "items": [],
            "date_creation": datetime.now(),
            "numero_facture": f"FAC-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        }
        
        # Récupérer les articles
        i = 0
        while f"items[{i}][description]" in request.form:
            item = {
                "description": request.form.get(f"items[{i}][description]", ""),
                "quantite": float(request.form.get(f"items[{i}][quantite]", 0)),
                "prix": float(request.form.get(f"items[{i}][prix]", 0)),
                "total": float(request.form.get(f"items[{i}][quantite]", 0)) * float(request.form.get(f"items[{i}][prix]", 0))
            }
            if item["description"]:
                facture_data["items"].append(item)
            i += 1
        
        # Calculer les totaux
        sous_total = sum(item["total"] for item in facture_data["items"])
        tva = sous_total * 0.20
        total_ttc = sous_total + tva
        
        facture_data["totaux"] = {
            "sous_total": sous_total,
            "tva": tva,
            "total_ttc": total_ttc
        }
        
        # Récupérer les infos du carnet si disponible
        if facture_data["carnet_id"]:
            try:
                carnet = db.carnets.find_one({"_id": ObjectId(facture_data["carnet_id"])})
                if carnet:
                    facture_data["animal"] = {
                        "nom": carnet.get("name", ""),
                        "espece": carnet.get("species", ""),
                        "race": carnet.get("breed", ""),
                        "proprietaire": carnet.get("proprietaire_nom", ""),
                        "adresse": carnet.get("proprietaire_adresse", ""),
                        "ville": f"{carnet.get('proprietaire_cp', '')} {carnet.get('proprietaire_ville', '')}",
                        "tel": carnet.get("proprietaire_tel", ""),
                        "email": carnet.get("proprietaire_email", "")
                    }
            except:
                pass
        
        # Sauvegarder dans la base de données
        inserted = db.factures.insert_one(facture_data)
        facture_data["_id"] = str(inserted.inserted_id)
        
        # Générer le PDF
        pdf_path = generate_facture_pdf(facture_data)
        
        # Nom du fichier
        nom_fichier = f"Facture_{facture_data['numero_facture']}_{facture_data.get('animal', {}).get('nom', 'Animal')}.pdf"
        
        return send_file(pdf_path, as_attachment=True, download_name=nom_fichier)
        
    except Exception as e:
        print(f"Erreur génération facture: {e}")
        return f"Erreur lors de la génération: {str(e)}", 500

# ==================== FONCTIONS DE GÉNÉRATION PDF CARTE IDENTIFICATION ====================

def generate_carte_identification_complete(data, carte_id):
    """Génère la carte d'identification complète (haute + basse)"""
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf_path = temp_file.name
    
    # Configuration du document
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        topMargin=1*cm,
        bottomMargin=1*cm,
        leftMargin=1*cm,
        rightMargin=1*cm,
        title=f"Carte Identification - {data.get('animalName', 'Animal')}"
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Couleurs officielles
    COLOR_PRIMARY = colors.black
    COLOR_SECONDARY = colors.HexColor('#666666')
    
    # Styles
    style_entreprise = ParagraphStyle(
        name='Entreprise',
        parent=styles['Normal'],
        fontSize=9,
        textColor=COLOR_PRIMARY,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    style_normal = ParagraphStyle(
        name='Normal',
        parent=styles['Normal'],
        fontSize=8,
        textColor=COLOR_PRIMARY,
        alignment=0,
        leading=10
    )
    
    style_label = ParagraphStyle(
        name='Label',
        parent=styles['Normal'],
        fontSize=8,
        textColor=COLOR_PRIMARY,
        fontName='Helvetica-Bold',
        spaceAfter=1
    )
    
    style_value = ParagraphStyle(
        name='Value',
        parent=styles['Normal'],
        fontSize=8,
        textColor=COLOR_PRIMARY
    )
    
    style_login = ParagraphStyle(
        name='Login',
        parent=styles['Normal'],
        fontSize=9,
        textColor=COLOR_PRIMARY,
        fontName='Helvetica-Bold',
        alignment=1,
        backColor=colors.HexColor('#F0F0F0'),
        borderPadding=6
    )
    
    style_section = ParagraphStyle(
        name='Section',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=COLOR_PRIMARY,
        fontName='Helvetica-Bold',
        spaceAfter=5,
        spaceBefore=10
    )
    
    # ===== PARTIE HAUTE =====
    
    # En-tête officiel
    header_text = "SOCIÉTÉ D'IDENTIFICATION DES CARNIVORES DOMESTIQUES<br/>112-114 Avenue Gabriel Péri - 94246 L'HAY LES ROSES Cedex<br/><b>0 810 778 778</b>"
    story.append(Paragraph(header_text, style_entreprise))
    story.append(Spacer(1, 0.3*cm))
    
    # Date
    date_heure = data['date_creation'].strftime('%d/%m/%Y %H:%M:%S')
    story.append(Paragraph(date_heure, ParagraphStyle(name='Date', fontSize=8, alignment=0)))
    story.append(Spacer(1, 0.3*cm))
    
    # Introduction
    intro_text = """Madame, Monsieur,<br/><br/>
    Nous avons le plaisir de vous adresser la carte d'identification de votre animal 
    suite à l'enregistrement de son identification et de vos coordonnées dans le 
    Fichier National des Carnivores Domestiques (chiens, chats, furets) :<br/>
    - La partie basse peut être détachée et conservée avec vous.<br/>
    - La partie haute est indispensable pour effectuer toutes les modifications 
    souhaitées dans notre base de données I-CaD."""
    story.append(Paragraph(intro_text, style_normal))
    story.append(Spacer(1, 0.3*cm))
    
    # Identifiant et mot de passe
    login_text = f"""Veuillez trouver ci-dessous l'identifiant et le mot de passe de votre animal. 
    Ils vous permettent d'effectuer un certain nombre de modifications directement 
    sur notre site www.i-cad.fr dans la rubrique « mes animaux » de l'espace Détenteur :<br/><br/>
    <b>IDENTIFIANT :</b> {data.get('animalId', '250269612345678')}<br/>
    <b>MOT DE PASSE :</b> {data.get('password', 'abcdef01')}"""
    story.append(Paragraph(login_text, style_login))
    story.append(Spacer(1, 0.3*cm))
    
    # Section Identification de l'animal
    story.append(Paragraph("IDENTIFICATION DE L'ANIMAL", style_section))
    
    # Informations propriétaire dans un tableau
    info_data = [
        ["Nom et prénom du propriétaire", data.get('ownerName', '')],
        ["Adresse complète du propriétaire", data.get('ownerAddress', '')],
        ["TEL 1", data.get('phone1', '')],
        ["E-MAIL", data.get('email', '')],
        ["VÉTÉRINAIRE TRAITANT", f"{data.get('veterinaireNom', '')} {data.get('veterinaireContact', '')}"],
        ["TEL 2", data.get('phone2', '')],
    ]
    
    info_table_data = []
    for label, value in info_data:
        if value and value.strip():
            info_table_data.append([
                Paragraph(f"<b>{label}</b>", style_label),
                Paragraph(value, style_value)
            ])
    
    if info_table_data:
        info_table = Table(info_table_data, colWidths=[5*cm, 11*cm])
        info_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('PADDING', (0,0), (-1,-1), 3),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(info_table)
    
    story.append(Spacer(1, 0.3*cm))
    
    # Section Identification
    story.append(Paragraph("IDENTIFICATION DE L'ANIMAL", style_section))
    
    # Données d'identification
    id_data = [
        ["INSEPT :", data.get('animalId', '250269612345678')],
        ["DATE :", format_date(data.get('idDate', ''))],
        ["EMPLACEMENT :", data.get('idLocation', 'GOUTTIERE JUGULAIRE GAUCHE')],
    ]
    
    id_table_data = []
    for label, value in id_data:
        id_table_data.append([
            Paragraph(f"<b>{label}</b>", style_label),
            Paragraph(value, style_value)
        ])
    
    id_table = Table(id_table_data, colWidths=[2.5*cm, 13.5*cm])
    id_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(id_table)
    
    story.append(Spacer(1, 0.3*cm))
    
    # Section Description
    espece_display = "CHAT"
    if data.get('animalEspece') == 'CHIEN':
        espece_display = 'CHIEN'
    elif data.get('animalEspece') == 'AUTRE':
        espece_display = 'AUTRE'
    
    story.append(Paragraph(f"DESCRIPTION DU {espece_display}", style_section))
    
    # Données description
    sex_display = "MÂLE" if data.get('sex') == 'MALE' else "FEMELLE"
    sterilise_display = "OUI" if data.get('sterilise') == 'OUI' else "NON"
    
    desc_data = [
        ["DATE DE NAISSANCE", format_date(data.get('birthDate', ''))],
        ["CATÉGORIE", data.get('categorie', 'Non spécifiée')],
        ["RACE", data.get('breed', 'EUROPEEN')],
        ["ROBE", data.get('coat', 'NOIR ET BLANC')],
        ["POIL", data.get('hairType', 'COURT')],
        ["SEXE", sex_display],
        ["NOM DE NAISSANCE", data.get('nomNaissance', 'Non spécifié')],
        ["STÉRILISÉ", sterilise_display],
        ["NOM D'USAGE", data.get('animalName', 'FELIX')],
        ["PAYS D'ORIGINE", data.get('paysOrigine', 'FRANCE')],
        ["SIGNES PARTICULIERS", data.get('specialMarks', 'Aucun')],
    ]
    
    desc_table_data = []
    for label, value in desc_data:
        desc_table_data.append([
            Paragraph(f"<b>{label}</b>", style_label),
            Paragraph(value, style_value)
        ])
    
    desc_table = Table(desc_table_data, colWidths=[4*cm, 12*cm])
    desc_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(desc_table)
    
    # Ligne de séparation pointillée
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, 
                          dash=[3, 3], spaceAfter=0.5*cm, spaceBefore=0.5*cm))
    
    # ===== PARTIE BASSE =====
    
    # Titre partie basse
    partie_basse_title = """PARTIE BASSE DE LA CARTE D'IDENTIFICATION À DÉTACHER ET À CONSERVER AVEC VOUS<br/>
    [ne sert en aucun cas à effectuer de modifications dans notre fichier ou de changement de détenteur]"""
    
    story.append(Paragraph(partie_basse_title, 
                         ParagraphStyle(name='PartieBasse', fontSize=8, alignment=1, 
                                      fontName='Helvetica-Bold')))
    story.append(Spacer(1, 0.3*cm))
    
    # Numéro réduit
    num_reduit = data.get('animalId', '250269612345678')
    if len(num_reduit) > 8:
        num_reduit = num_reduit[-8:]
    
    # Informations partie basse
    info_basse_text = f"""
    <b>IDENTIFICATION : {data.get('animalId', '250269612345678')}</b><br/>
    <b>NOM DU PROPRIETAIRE : {data.get('ownerName', 'Nom du propriétaire')}<br/><br/>
    <b>ADRESSE DU PROPRIETAIRE : {data.get('ownerAddress', 'Adresse complète du propriétaire')}<br/><br/>
    <b>NOM : {data.get('animalName', 'FELIX').upper()}</b><br/>
    <b>NÉ(E) LE : {format_date(data.get('birthDate', ''))}</b><br/>
    <b>RACE : {data.get('breed', 'EUROPEEN').upper()}</b><br/>
    <b>ROBE : {data.get('coat', 'NOIR ET BLANC').upper()}</b>
    """
    
    # Tableau pour la partie basse
    basse_data = [
        [Paragraph(num_reduit, ParagraphStyle(name='NumReduit', fontSize=14, 
                                            fontName='Helvetica-Bold', alignment=1)),
         Paragraph(info_basse_text, ParagraphStyle(name='InfoBasse', fontSize=8))]
    ]
    
    basse_table = Table(basse_data, colWidths=[4*cm, 12*cm])
    basse_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (0,0), 'MIDDLE'),
        ('VALIGN', (1,0), (1,0), 'TOP'),
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#F8F8F8')),
    ]))
    
    story.append(basse_table)
    
    # ===== GÉNÉRATION =====
    
    try:
        doc.build(story)
        print(f"✅ Carte identification complète générée: {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"❌ Erreur génération carte: {e}")
        error_doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        error_story = [Paragraph(f"Erreur: {str(e)}", style_normal)]
        error_doc.build(error_story)
        return pdf_path

def generate_carte_identification_haute(data, carte_id):
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_path = temp_file.name

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=1.2*cm,
        rightMargin=1.2*cm,
        topMargin=1.2*cm,
        bottomMargin=1.2*cm
    )

    story = []
    styles = getSampleStyleSheet()

    # ===== COULEURS I-CAD =====
    BLUE_DARK = colors.HexColor("#2F4858")
    BLUE_LIGHT = colors.HexColor("#F4F8FB")
    BLUE_BORDER = colors.HexColor("#4A90E2")

    # ===== EN-TÊTE =====
    header = Table(
        [[Paragraph(
            """<font color="white"><b>SOCIÉTÉ D’IDENTIFICATION DES CARNIVORES DOMESTIQUES</b><br/>
            112-114 Avenue Gabriel Péri – 94246 L’Haÿ-les-Roses Cedex<br/>
            <b>0 810 778 778</b></font>""",
            ParagraphStyle(
                name="HeaderText",
                alignment=1,
                fontSize=9,
                leading=12
            )
        )]],
        colWidths=[17*cm],
        rowHeights=[2.2*cm]
    )

    header.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BLUE_DARK),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.5*cm))

    # ===== INTRO =====
    story.append(Paragraph(
        "Madame, Monsieur,<br/><br/>"
        "Nous avons le plaisir de vous adresser la carte d’identification de votre animal "
        "suite à l’enregistrement de son identification et de vos coordonnées dans le "
        "Fichier National des Carnivores Domestiques (chiens, chats, furets).",
        ParagraphStyle(
            name="Intro",
            fontSize=8.5,
            leading=12
        )
    ))
    story.append(Spacer(1, 0.4*cm))

    # ===== BLOC IDENTIFIANT =====
    login = Table(
        [[Paragraph(
            f"<b>IDENTIFIANT :</b> {data.get('animalId','')}<br/>"
            f"<b>MOT DE PASSE :</b> {data.get('password','')}",
            ParagraphStyle(
                name="Login",
                fontSize=9,
                leading=14
            )
        )]],
        colWidths=[17*cm]
    )

    login.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BLUE_LIGHT),
        ('LINEBEFORE', (0,0), (0,0), 4, BLUE_BORDER),
        ('BOX', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(login)
    story.append(Spacer(1, 0.6*cm))

    # ===== FONCTION BLOC SECTION =====
    def section(title, rows):
        bloc = [[Paragraph(f"<b>{title}</b>",
                 ParagraphStyle(name="SectionTitle", fontSize=9))]]
        for label, value in rows:
            bloc.append([
                Paragraph(f"<b>{label}</b>", ParagraphStyle(name="Lbl", fontSize=8)),
                Paragraph(value or "", ParagraphStyle(name="Val", fontSize=8))
            ])

        t = Table(bloc, colWidths=[6*cm, 11*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
            ('BACKGROUND', (0,1), (-1,-1), BLUE_LIGHT),
            ('LINEBEFORE', (0,0), (0,-1), 4, BLUE_BORDER),
            ('GRID', (0,0), (-1,-1), 0.3, colors.lightgrey),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        return t

    # ===== DONNÉES =====
    story.append(section("IDENTIFICATION DU PROPRIÉTAIRE", [
        ("Nom et prénom", data.get("ownerName","")),
        ("Adresse", data.get("ownerAddress","")),
        ("Téléphone", data.get("phone1","")),
        ("Email", data.get("email","")),
    ]))
    story.append(Spacer(1, 0.4*cm))

    story.append(section("IDENTIFICATION DE L’ANIMAL", [
        ("N°", data.get("animalId","")),
        ("Date", format_date(data.get("idDate",""))),
        ("Emplacement", data.get("idLocation","")),
    ]))
    story.append(Spacer(1, 0.4*cm))

    story.append(section("DESCRIPTION DE L’ANIMAL", [
        ("Nom", data.get("animalName","")),
        ("Date de naissance", format_date(data.get("birthDate",""))),
        ("Race", data.get("breed","")),
        ("Robe", data.get("coat","")),
        ("Sexe", data.get("sex","")),
        ("Stérilisé", data.get("sterilise","")),
    ]))

    # ===== FOOTER =====
    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph(
        "Document généré automatiquement – Veterinary Pro",
        ParagraphStyle(
            name="Footer",
            fontSize=7,
            alignment=1,
            textColor=colors.grey
        )
    ))

    doc.build(story)
    return pdf_path


def generate_carte_identification_basse(data, carte_id):

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_path = temp_file.name

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    story = []

    # ===== TITRE =====
    story.append(Paragraph(
        "PARTIE BASSE DE LA CARTE D'IDENTIFICATION À DÉTACHER<br/>ET À CONSERVER AVEC VOUS",
        ParagraphStyle(
            name="Titre",
            fontName="Helvetica-Bold",
            fontSize=12,
            alignment=1,
            textColor=colors.HexColor("#1F3A5F"),
            leading=16,
            spaceAfter=10
        )
    ))

    # ===== SOUS TEXTE =====
    story.append(Paragraph(
        "[ne sert en aucun cas à effectuer de modifications dans notre fichier ou de<br/>changement de détenteur]",
        ParagraphStyle(
            name="SousTitre",
            fontSize=9,
            alignment=1,
            textColor=colors.grey,
            italic=True,
            spaceAfter=16
        )
    ))

    # ===== LIGNE DE DÉCOUPE =====
    decoupe = Table([[" "]], colWidths=[16*cm])
    decoupe.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,-1), 1, colors.HexColor("#B0BEC5"), None, (4,4)),
    ]))
    story.append(decoupe)
    story.append(Spacer(1, 1*cm))

    # ===== NUMÉRO RÉDUIT =====
    full_id = data.get("animalId", "250269612345678")
    num_reduit = full_id[-8:]

    bloc_num = Table(
        [[Paragraph(
            num_reduit,
            ParagraphStyle(
                name="Num",
                fontName="Helvetica-Bold",
                fontSize=20,
                alignment=1,
                textColor=colors.HexColor("#2E86DE")
            )
        )]],
        colWidths=[4*cm],
        rowHeights=[3*cm]
    )

    bloc_num.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EEF6FD")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOX', (0,0), (-1,-1), 2, colors.white),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))

    # ===== INFOS DROITE =====
    infos = f"""
    <b>NOM DE L'ANIMAL : </b><font size="14"><b>{data.get('animalName', '').upper()}</b></font><br/><br/>

    <b>IDENTIFICATION :</b> {full_id}<br/>
    <b>NOM DU PROPRIÉTAIRE :</b> {data.get('ownerName', '')}<br/>
    <b>NÉ(E) LE :</b> {format_date(data.get('birthDate', ''))}<br/>
    <b>RACE :</b> {data.get('breed', '').upper()}<br/>
    <b>COULEUR :</b> {data.get('coat', '').upper()}
    """

    bloc_infos = Paragraph(
        infos,
        ParagraphStyle(
            name="Infos",
            fontSize=9.5,
            leading=15,
            textColor=colors.HexColor("#263238"),
            alignment=2
        )
    )

    # ===== CARTE PRINCIPALE =====
    carte = Table(
        [[bloc_num, bloc_infos]],
        colWidths=[5*cm, 11*cm],
        rowHeights=[4*cm]
    )

    carte.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#B0BEC5")),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('LEFTPADDING', (0,0), (-1,-1), 16),
        ('RIGHTPADDING', (0,0), (-1,-1), 16),
        ('TOPPADDING', (0,0), (-4,-4), 18),
        ('BOTTOMPADDING', (0,0), (-4,-4), 18),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))

    story.append(carte)

    # ===== PIED DE PAGE =====
    story.append(Spacer(1, 1.2*cm))
    story.append(Paragraph(
        f"Carte générée le {datetime.now().strftime('%d/%m/%Y')} – Document informatif",
        ParagraphStyle(
            name="Footer",
            fontSize=8,
            alignment=1,
            textColor=colors.grey
        )
    ))

    doc.build(story)
    return pdf_path


# ==================== FONCTIONS DE GÉNÉRATION PDF EXISTANTES ====================

def generate_health_book_pdf(data, carnet_id):
    """Génère un carnet de santé professionnel et complet"""
    
    # Créer un nom de fichier temporaire
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf_path = temp_file.name
    
    # Configuration du document
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        topMargin=2*cm,
        bottomMargin=2*cm,
        leftMargin=2*cm,
        rightMargin=2*cm,
        title=f"Carnet de Santé - {data.get('name', 'Animal')}"
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # ===== STYLES PERSONNALISÉS PROFESSIONNELS =====
    
    # Couleurs professionnelles
    COLOR_PRIMARY = colors.HexColor('#2C3E50')      # Bleu foncé
    COLOR_SECONDARY = colors.HexColor('#3498DB')    # Bleu
    COLOR_ACCENT = colors.HexColor('#E74C3C')       # Rouge
    COLOR_SUCCESS = colors.HexColor('#27AE60')      # Vert
    COLOR_WARNING = colors.HexColor('#F39C12')      # Orange
    COLOR_LIGHT = colors.HexColor('#F8F9FA')        # Gris clair
    
    # Style titre principal
    style_main_title = ParagraphStyle(
        name='MainTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=COLOR_PRIMARY,
        alignment=1,
        spaceAfter=20,
        spaceBefore=0,
        fontName='Helvetica-Bold',
        underlineWidth=1,
        underlineColor=COLOR_SECONDARY
    )
    
    # Style titre de section
    style_section_title = ParagraphStyle(
        name='SectionTitle',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=COLOR_PRIMARY,
        alignment=0,
        spaceAfter=15,
        spaceBefore=25,
        fontName='Helvetica-Bold',
        borderPadding=8,
        borderColor=COLOR_SECONDARY,
        borderWidth=1,
        borderRadius=5,
        backColor=colors.HexColor('#E8F4F8')
    )
    
    # Style sous-section
    style_subsection = ParagraphStyle(
        name='Subsection',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=COLOR_SECONDARY,
        alignment=0,
        spaceAfter=10,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    # Style texte normal
    style_normal = ParagraphStyle(
        name='Normal',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        textColor=colors.black,
        alignment=0
    )
    
    # Style pour labels
    style_label = ParagraphStyle(
        name='Label',
        parent=styles['Normal'],
        fontSize=10,
        textColor=COLOR_PRIMARY,
        fontName='Helvetica-Bold',
        spaceAfter=3
    )
    
    # Style pour valeurs
    style_value = ParagraphStyle(
        name='Value',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        backColor=COLOR_LIGHT,
        borderPadding=8,
        borderColor=colors.HexColor('#EEEEEE'),
        borderWidth=1,
        borderRadius=3
    )
    
    # Style pour les tableaux d'en-tête
    style_table_header = ParagraphStyle(
        name='TableHeader',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.white,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    # ===== FONCTION POUR CRÉER DES SECTIONS =====
    def create_section(title, content, with_border=True):
        """Crée une section structurée"""
        section_elements = []
        
        # Titre de section
        title_para = Paragraph(f"<b>{title}</b>", style_section_title)
        section_elements.append(title_para)
        
        # Ligne de séparation
        if with_border:
            line = HRFlowable(
                width="100%", 
                thickness=1, 
                color=COLOR_SECONDARY,
                spaceAfter=10,
                spaceBefore=5
            )
            section_elements.append(line)
        
        # Contenu
        if isinstance(content, list):
            for item in content:
                section_elements.append(item)
        else:
            section_elements.append(content)
            
        return section_elements
    
    def create_info_row(label, value, col_widths=[5*cm, 11*cm]):
        """Crée une ligne d'information"""
        if not value:
            return None
            
        data = [[
            Paragraph(f"<b>{label}</b>", style_label),
            Paragraph(value, style_value)
        ]]
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (0,-1), 5),
            ('RIGHTPADDING', (1,0), (1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        
        return table
    
    # ===== PAGE DE GARDE =====
    
    # En-tête professionnel
    header_data = [
        [Paragraph("CLINIQUE VÉTÉRINAIRE", 
                  ParagraphStyle(name='HeaderLeft', fontSize=12, textColor=COLOR_PRIMARY, alignment=0)),
         Paragraph("CARNET DE SANTÉ", 
                  ParagraphStyle(name='HeaderRight', fontSize=12, textColor=COLOR_PRIMARY, alignment=2))]
    ]
    
    header_table = Table(header_data, colWidths=[10*cm, 6*cm])
    header_table.setStyle(TableStyle([
        ('BOTTOMPADDING', (0,0), (-1,-1), 15),
        ('LINEBELOW', (0,0), (-1,0), 1, COLOR_SECONDARY),
    ]))
    
    story.append(header_table)
    story.append(Spacer(1, 3*cm))
    
    # Titre principal
    story.append(Paragraph(
        "📋 CARNET DE SANTÉ ANIMAL",
        style_main_title
    ))
    story.append(Spacer(1, 2*cm))
    
    # Nom de l'animal en évidence
    if data.get('name'):
        style_animal_name = ParagraphStyle(
            name='AnimalName',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=COLOR_ACCENT,
            alignment=1,
            spaceAfter=2*cm,
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph(data['name'].upper(), style_animal_name))
    
    # Photo de l'animal
    if data.get('photo') and os.path.exists(data['photo']):
        try:
            img = Image(data['photo'], width=10*cm, height=10*cm)
            img.hAlign = 'CENTER'
            
            # Cadre pour la photo
            photo_frame = Table([[img]], colWidths=[12*cm])
            photo_frame.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (0,0), colors.white),
                ('PADDING', (0,0), (0,0), 10),
                ('BOX', (0,0), (0,0), 2, COLOR_SECONDARY),
                ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ]))
            
            story.append(photo_frame)
            story.append(Spacer(1, 2*cm))
        except Exception as e:
            print(f"Erreur photo: {e}")
    
    # Informations principales
    infos_principales = []
    if data.get('species'):
        infos_principales.append(["Espèce", data['species']])
    if data.get('breed'):
        infos_principales.append(["Race", data['breed']])
    if data.get('age'):
        infos_principales.append(["Âge", data['age']])
    if data.get('identification'):
        infos_principales.append(["Identification", data['identification']])
    
    if infos_principales:
        data_table = []
        for label, value in infos_principales:
            data_table.append([
                Paragraph(f"<b>{label}</b>", 
                         ParagraphStyle(name='InfoLabel', fontSize=12, textColor=colors.white, 
                                      fontName='Helvetica-Bold', alignment=1)),
                Paragraph(value, 
                         ParagraphStyle(name='InfoValue', fontSize=12, textColor=colors.black, alignment=1))
            ])
        
        table = Table(data_table, colWidths=[6*cm, 6*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), COLOR_SECONDARY),
            ('BACKGROUND', (1,0), (1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
            ('PADDING', (0,0), (-1,-1), 12),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        
        story.append(table)
    
    # Informations propriétaire
    story.append(Spacer(1, 3*cm))
    if data.get('proprietaire_nom'):
        story.append(Paragraph(
            f"<b>Propriétaire :</b> {data['proprietaire_nom']}",
            ParagraphStyle(name='Proprio', fontSize=12, textColor=COLOR_PRIMARY, alignment=1)
        ))
    
    # Pied de page première page
    story.append(Spacer(1, 4*cm))
    story.append(Paragraph(
        f"<i>Numéro de carnet : {carnet_id[:8]} • Créé le {datetime.now().strftime('%d/%m/%Y')}</i>",
        ParagraphStyle(name='FooterInfo', fontSize=10, textColor=colors.grey, alignment=1)
    ))
    
    story.append(PageBreak())
    
    # ===== PAGE 2 : IDENTITÉ COMPLÈTE =====
    
    # Section identité
    identite_content = []
    
    identite_rows = []
    if data.get('name'):
        identite_rows.append(create_info_row("Nom", data['name']))
    if data.get('species'):
        identite_rows.append(create_info_row("Espèce", data['species']))
    if data.get('breed'):
        identite_rows.append(create_info_row("Race", data['breed']))
    if data.get('age'):
        identite_rows.append(create_info_row("Âge", data['age']))
    if data.get('sex'):
        identite_rows.append(create_info_row("Sexe", data['sex']))
    if data.get('sterilise'):
        identite_rows.append(create_info_row("Stérilisé(e)", data['sterilise']))
    if data.get('poids'):
        identite_rows.append(create_info_row("Poids", f"{data['poids']} kg"))
    if data.get('identification'):
        identite_rows.append(create_info_row("Numéro d'identification", data['identification']))
    
    for row in identite_rows:
        if row:
            identite_content.append(row)
            identite_content.append(Spacer(1, 0.3*cm))
    
    story.extend(create_section(
        "👤 IDENTITÉ DE L'ANIMAL",
        identite_content
    ))
    
    story.append(Spacer(1, 1*cm))
    
    # Section propriétaire
    proprio_content = []
    
    if data.get('proprietaire_nom'):
        proprio_content.append(create_info_row("Nom", data['proprietaire_nom']))
    if data.get('proprietaire_tel'):
        proprio_content.append(create_info_row("Téléphone", data['proprietaire_tel']))
    if data.get('proprietaire_email'):
        proprio_content.append(create_info_row("Email", data['proprietaire_email']))
    if data.get('proprietaire_adresse'):
        adresse = data['proprietaire_adresse']
        if data.get('proprietaire_cp'):
            adresse += f", {data['proprietaire_cp']}"
        if data.get('proprietaire_ville'):
            adresse += f" {data['proprietaire_ville']}"
        proprio_content.append(create_info_row("Adresse", adresse))
    
    for item in proprio_content:
        if item:
            story.append(item)
            story.append(Spacer(1, 0.3*cm))
    
    story.append(PageBreak())
    
    # ===== PAGE 3 : SANTÉ ET VACCINATIONS =====
    
    # Section santé
    sante_content = []
    
    if data.get('allergies'):
        sante_content.append(Paragraph("Allergies connues", style_subsection))
        sante_content.append(Paragraph(data['allergies'], style_normal))
        sante_content.append(Spacer(1, 0.5*cm))
    
    if data.get('antecedents'):
        sante_content.append(Paragraph("Antécédents médicaux", style_subsection))
        sante_content.append(Paragraph(data['antecedents'], style_normal))
        sante_content.append(Spacer(1, 0.5*cm))
    
    if data.get('traitement'):
        sante_content.append(Paragraph("Traitement en cours", style_subsection))
        sante_content.append(Paragraph(data['traitement'], style_normal))
        sante_content.append(Spacer(1, 0.5*cm))
    
    if sante_content:
        story.extend(create_section(
            "💊 INFORMATIONS DE SANTÉ",
            sante_content
        ))
    
    # Vaccinations
    if data.get('vaccins'):
        story.append(Paragraph("Vaccinations", style_subsection))
        
        vaccins_data = []
        headers = ["Vaccin", "Date", "Rappel", "N° Lot"]
        vaccins_data.append([
            Paragraph(f"<b>{h}</b>", style_table_header) for h in headers
        ])
        
        for vaccin in data['vaccins']:
            vaccins_data.append([
                Paragraph(vaccin.get('type', ''), style_normal),
                Paragraph(vaccin.get('date', ''), style_normal),
                Paragraph(vaccin.get('rappel', ''), style_normal),
                Paragraph(vaccin.get('lot', ''), style_normal)
            ])
        
        if len(vaccins_data) > 1:
            table_vaccins = Table(vaccins_data, colWidths=[5*cm, 3*cm, 3*cm, 5*cm])
            table_vaccins.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), COLOR_SECONDARY),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#EEEEEE')),
                ('ALIGN', (1,0), (2,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('PADDING', (0,0), (-1,-1), 8),
                ('FONTSIZE', (0,0), (-1,-1), 9),
            ]))
            
            story.append(table_vaccins)
            story.append(Spacer(1, 1*cm))
    
    # Antiparasitaires
    if data.get('antiparasitaires'):
        story.append(Paragraph("Traitements antiparasitaires", style_subsection))
        
        antiparas_data = []
        headers = ["Type", "Produit", "Date", "Prochaine date"]
        antiparas_data.append([
            Paragraph(f"<b>{h}</b>", style_table_header) for h in headers
        ])
        
        for antipara in data['antiparasitaires']:
            antiparas_data.append([
                Paragraph(antipara.get('type', ''), style_normal),
                Paragraph(antipara.get('produit', ''), style_normal),
                Paragraph(antipara.get('date', ''), style_normal),
                Paragraph(antipara.get('prochaine_date', ''), style_normal)
            ])
        
        if len(antiparas_data) > 1:
            table_antiparas = Table(antiparas_data, colWidths=[4*cm, 5*cm, 3*cm, 4*cm])
            table_antiparas.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), COLOR_SUCCESS),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#EEEEEE')),
                ('ALIGN', (2,0), (3,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('PADDING', (0,0), (-1,-1), 8),
                ('FONTSIZE', (0,0), (-1,-1), 9),
            ]))
            
            story.append(table_antiparas)
    
    story.append(PageBreak())
    
    # ===== PAGE 5 : CONTACTS ET PAGES DE CONSULTATION =====
    
    # Informations cabinet vétérinaire
    if data.get('veterinaire_cabinet'):
        cabinet_content = []
        
        if data.get('veterinaire_cabinet'):
            cabinet_content.append(create_info_row("Cabinet", data['veterinaire_cabinet']))
        if data.get('veterinaire_tel'):
            cabinet_content.append(create_info_row("Téléphone", data['veterinaire_tel']))
        if data.get('veterinaire_adresse'):
            cabinet_content.append(create_info_row("Adresse", data['veterinaire_adresse']))
        if data.get('veterinaire_email'):
            cabinet_content.append(create_info_row("Email", data['veterinaire_email']))
        
        story.extend(create_section(
            "🏥 CABINET VÉTÉRINAIRE",
            cabinet_content
        ))
    
    # Contact d'urgence
    contact_info = f"""
    <b>Contact d'urgence :</b><br/>
    {data.get('proprietaire_nom', '')}<br/>
    Tél: {data.get('proprietaire_tel', 'Non renseigné')}<br/>
    <br/>
    <b>Vétérinaire traitant :</b><br/>
    {data.get('veterinaire_cabinet', 'Non spécifié')}<br/>
    Tél: {data.get('veterinaire_tel', 'Non renseigné')}
    """
    
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(
        contact_info,
        ParagraphStyle(
            name='ContactInfo',
            fontSize=11,
            borderWidth=1,
            borderColor=COLOR_SECONDARY,
            borderPadding=15,
            backColor=colors.HexColor('#F8F9FA')
        )
    ))
    
    # ===== PAGES DE CONSULTATIONS =====
    for page_num in range(3):  # 3 pages de consultation
        story.append(PageBreak())
        
        story.extend(create_section(
            f"📝 JOURNAL DES CONSULTATIONS - Page {page_num + 1}",
            []
        ))
        
        # Tableau pour les consultations
        consult_data = []
        headers = ["Date", "Motif", "Traitement", "Observations", "Vétérinaire", "Signature"]
        consult_data.append([
            Paragraph(f"<b>{h}</b>", 
                     ParagraphStyle(name='ConsultHeader', fontSize=9, alignment=1, 
                                  fontName='Helvetica-Bold', textColor=colors.white)) 
            for h in headers
        ])
        
        # 15 lignes par page
        for i in range(15):
            consult_data.append([
                Paragraph("", ParagraphStyle(name='ConsultCell', fontSize=9)),
                Paragraph("", ParagraphStyle(name='ConsultCell', fontSize=9)),
                Paragraph("", ParagraphStyle(name='ConsultCell', fontSize=9)),
                Paragraph("", ParagraphStyle(name='ConsultCell', fontSize=9)),
                Paragraph("", ParagraphStyle(name='ConsultCell', fontSize=9)),
                Paragraph("", ParagraphStyle(name='ConsultCell', fontSize=9)),
            ])
        
        consult_table = Table(consult_data, colWidths=[2*cm, 3.5*cm, 3*cm, 3.5*cm, 2.5*cm, 2.5*cm])
        consult_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#EEEEEE')),
            ('PADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('MINIMUMHEIGHT', (0,1), (-1,-1), 0.8*cm),
        ]))
        
        story.append(consult_table)
        
        # Instruction
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(
            "<i>À compléter par le vétérinaire lors de chaque consultation. Conserver ce carnet avec vos documents importants.</i>",
            ParagraphStyle(
                name='Instruction',
                fontSize=9,
                textColor=colors.grey,
                alignment=2
            )
        ))
    
    # ===== CONSTRUCTION DU PDF =====
    try:
        doc.build(story)
        print(f"✅ Carnet de santé généré avec succès : {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"❌ Erreur génération carnet: {e}")
        # PDF d'erreur
        error_doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        error_story = [
            Paragraph("ERREUR DE GÉNÉRATION", style_main_title),
            Spacer(1, 2*cm),
            Paragraph(f"Erreur: {str(e)}", style_normal)
        ]
        error_doc.build(error_story)
        return pdf_path

def generate_facture_pdf(facture_data):
    """Génère un PDF professionnel pour la facture de livraison"""
    
    # Créer un nom de fichier temporaire
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf_path = temp_file.name
    
    # Configuration du document
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        title=f"Facture {facture_data['numero_facture']}"
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Couleurs professionnelles
    COLOR_PRIMARY = colors.HexColor('#198754')      # Vert
    COLOR_SECONDARY = colors.HexColor('#2C3E50')    # Bleu foncé
    COLOR_ACCENT = colors.HexColor('#FF6B6B')       # Rouge clair
    COLOR_LIGHT = colors.HexColor('#F8F9FA')        # Gris clair
    
    # Styles personnalisés
    style_titre = ParagraphStyle(
        name='TitrePrincipal',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=COLOR_PRIMARY,
        alignment=1,
        spaceAfter=5,
        fontName='Helvetica-Bold'
    )
    
    style_sous_titre = ParagraphStyle(
        name='SousTitre',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=COLOR_SECONDARY,
        alignment=1,
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )
    
    style_info = ParagraphStyle(
        name='Info',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        alignment=0
    )
    
    style_label = ParagraphStyle(
        name='Label',
        parent=styles['Normal'],
        fontSize=9,
        textColor=COLOR_SECONDARY,
        fontName='Helvetica-Bold',
        spaceAfter=2
    )
    
    style_value = ParagraphStyle(
        name='Value',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black
    )
    
    # ===== EN-TÊTE DE LA FACTURE =====
    
    # Logo et informations entreprise
    header_data = [
        [
            Paragraph(f"<b>{facture_data['entreprise']['nom']}</b><br/>"
                     f"{facture_data['entreprise']['cp']} {facture_data['entreprise']['ville']}<br/>"
                     f"{facture_data['entreprise']['cp1']} {facture_data['entreprise']['ville1']}<br/>"
                     f"{facture_data['entreprise']['cp2']} {facture_data['entreprise']['ville2']}<br/>"
                     f"Tél: {facture_data['entreprise']['tel']} • Email: {facture_data['entreprise']['email']}<br/>"
                     f"TVA: {facture_data['entreprise']['tva']}",
                     ParagraphStyle(name='Entreprise', fontSize=10)),
            Paragraph(f"<b>FACTURE</b><br/>"
                     f"<font size='13'><b>{facture_data['numero_facture']}</b></font><br/>"
                     f"Date: {facture_data['date_creation'].strftime('%d/%m/%Y')}",
                     ParagraphStyle(name='FactureInfo', fontSize=12, alignment=2))
        ]
    ]
    
    header_table = Table(header_data, colWidths=[10*cm, 6*cm])
    header_table.setStyle(TableStyle([
        ('BOTTOMPADDING', (0,0), (-1,-1), 15),
        ('LINEBELOW', (0,0), (-1,0), 2, COLOR_PRIMARY),
    ]))
    
    story.append(header_table)
    story.append(Spacer(1, 1*cm))
    
    # ===== INFORMATIONS CLIENT ET LIVRAISON =====
    
    # Section client
    client_info = []
    if 'client' in facture_data and facture_data['client']['nom']:
        client_info.append(Paragraph(
            f"<b>Nom:</b> {facture_data['client']['nom']}<br/>"
            f"<b>Adresse:</b> {facture_data['client']['adresse']}<br/>"
            f"<b>Ville:</b> {facture_data['client']['cp']} {facture_data['client']['ville']}<br/>"
            f"<b>Téléphone:</b> {facture_data['client']['tel']}<br/>"
            f"<b>Email:</b> {facture_data['client']['email']}",
            style_value
        ))
    
    # Section livraison
    livraison_info = []
    
    # Informations de l'animal
    animal_info = ""
    if 'animal' in facture_data:
        animal_info = f"<b>Animal:</b> {facture_data['animal']['nom']} ({facture_data['animal']['espece']} - {facture_data['animal']['race']})<br/>"
    elif facture_data['livraison']['espece'] or facture_data['livraison']['race']:
        animal_info = f"<b>Animal:</b> {facture_data['livraison']['espece']} - {facture_data['livraison']['race']}<br/>"
    
    livraison_info.append(Paragraph(
        f"{animal_info}"
        f"<b>Date:</b> {facture_data['livraison']['date']}<br/>"
        f"<b>Heure prise en charge:</b> {facture_data['livraison']['heure_prise']}<br/>"
        f"<b>Heure livraison estimée:</b> {facture_data['livraison']['heure_livraison']}",
        style_value
    ))
    
    if facture_data['livraison']['notes']:
        livraison_info.append(Spacer(1, 0.3*cm))
        livraison_info.append(Paragraph(f"<b>Notes:</b> {facture_data['livraison']['notes']}", 
                                       ParagraphStyle(name='Notes', fontSize=9, fontStyle='italic')))
    
    # Tableau deux colonnes alignées
    infos_table = Table([
        [Paragraph("<b>INFORMATIONS DU CLIENT</b>", 
                  ParagraphStyle(name='SectionHeader', fontSize=11, 
                               fontName='Helvetica-Bold', alignment=0)),
         Paragraph("<b>DÉTAILS DE LA LIVRAISON</b>", 
                  ParagraphStyle(name='SectionHeader', fontSize=11, 
                               fontName='Helvetica-Bold', alignment=0))],
        [client_info, livraison_info]
    ], colWidths=[8*cm, 8*cm])
    
    infos_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_LIGHT),
        ('GRID', (0,0), (-1,1), 0.5, COLOR_LIGHT),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,0), 'LEFT'),
    ]))
    
    story.append(infos_table)
    story.append(Spacer(1, 0.8*cm))
    
    # ===== DÉTAILS DES ARTICLES =====
    
    story.append(Paragraph("<b>DÉTAILS DES PRESTATIONS</b>", 
                          ParagraphStyle(name='SectionTitre', fontSize=11, 
                                        fontName='Helvetica-Bold', spaceAfter=10)))
    
    # Tableau des articles
    articles_data = [["Description", "Qté", "Prix unitaire", "Total HT"]]
    
    for item in facture_data['items']:
        articles_data.append([
            Paragraph(item['description'], style_value),
            Paragraph(str(item['quantite']), ParagraphStyle(name='Center', fontSize=10, alignment=1)),
            Paragraph(f"{item['prix']:.2f} €", ParagraphStyle(name='Right', fontSize=10, alignment=2)),
            Paragraph(f"{item['total']:.2f} €", ParagraphStyle(name='Right', fontSize=10, alignment=2))
        ])
    
    articles_table = Table(articles_data, colWidths=[9*cm, 2*cm, 3*cm, 2*cm])
    articles_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, COLOR_LIGHT),
        ('ALIGN', (1,1), (3,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    story.append(articles_table)
    story.append(Spacer(1, 1*cm))
    
    # ===== TOTAUX =====
    
    totaux_data = [
        ["", ""],
        ["Sous-total HT:", f"{facture_data['totaux']['sous_total']:.2f} €"],
        ["TVA (20%):", f"{facture_data['totaux']['tva']:.2f} €"],
        ["TOTAL TTC:", f"{facture_data['totaux']['total_ttc']:.2f} €"]
    ]
    
    totaux_table = Table(totaux_data, colWidths=[10*cm, 6*cm])
    totaux_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,3), (-1,3), 'Helvetica-Bold'),
        ('FONTSIZE', (0,3), (-1,3), 12),
        ('PADDING', (0,0), (-1,-1), 10),
        ('LINEABOVE', (0,3), (-1,3), 1, colors.black),
        ('BACKGROUND', (0,3), (-1,3), colors.HexColor('#E8F5E9')),
    ]))
    
    story.append(totaux_table)
    story.append(Spacer(1, 1.5*cm))
    
    # ===== CONDITIONS ET MENTIONS =====
    
    conditions_content = f"""
    <b>Conditions de paiement:</b> {facture_data['paiement']['conditions']}<br/><br/>
    <b>Mentions:</b> {facture_data['paiement']['mentions']}<br/><br/>
    <i>Facture émise le {facture_data['date_creation'].strftime('%d/%m/%Y à %H:%M')}</i>
    """
    
    conditions_frame = Table([[Paragraph(conditions_content, 
                                       ParagraphStyle(name='Conditions', fontSize=9))]], 
                            colWidths=[16*cm])
    conditions_frame.setStyle(TableStyle([
        ('BOX', (0,0), (0,0), 0.5, COLOR_LIGHT),
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#F9F9F9')),
        ('PADDING', (0,0), (0,0), 15),
    ]))
    
    story.append(conditions_frame)
    
    # ===== PIED DE PAGE =====
    
    story.append(Spacer(1, 3*cm))
    
    footer_content = f"""
    {facture_data['entreprise']['nom']} • {facture_data['entreprise']['cp']} {facture_data['entreprise']['ville']} • {facture_data['entreprise']['cp1']} {facture_data['entreprise']['ville1']} • {facture_data['entreprise']['cp2']} {facture_data['entreprise']['ville2']}<br/>
    Tél: {facture_data['entreprise']['tel']} • Email: {facture_data['entreprise']['email']}
    """
    
    story.append(Paragraph(footer_content, 
                          ParagraphStyle(name='Footer', fontSize=8, textColor=colors.grey, alignment=1)))
    
    # ===== GÉNÉRATION =====
    
    try:
        doc.build(story)
        print(f"✅ Facture générée: {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"❌ Erreur génération facture: {e}")
        # PDF d'erreur
        error_doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        error_story = [
            Paragraph("ERREUR DE GÉNÉRATION", style_titre),
            Spacer(1, 2*cm),
            Paragraph(f"Erreur: {str(e)}", ParagraphStyle(name='Error', fontSize=10))
        ]
        error_doc.build(error_story)
        return pdf_path

def generate_attestation_pdf(data, attestation_id):
    """Génère un PDF professionnel pour l'attestation vétérinaire"""
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf_path = temp_file.name
    
    # Configuration du document
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        topMargin=1*cm,
        bottomMargin=1*cm,
        leftMargin=1*cm,
        rightMargin=1*cm,
        title=f"Attestation Vétérinaire - {data.get('animal_name', 'Animal')}"
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Couleurs professionnelles
    COLOR_PRIMARY = colors.HexColor('#2C3E50')      # Bleu foncé
    COLOR_SECONDARY = colors.HexColor('#3498DB')    # Bleu
    COLOR_ACCENT = colors.HexColor('#E74C3C')       # Rouge
    COLOR_SUCCESS = colors.HexColor('#27AE60')      # Vert
    COLOR_LIGHT = colors.HexColor('#F8F9FA')        # Gris clair
    
    # Styles personnalisés
    style_main_title = ParagraphStyle(
        name='MainTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=COLOR_PRIMARY,
        alignment=1,
        spaceAfter=18,
        spaceBefore=0,
        fontName='Helvetica-Bold',
        underlineWidth=1,
        underlineColor=COLOR_SECONDARY
    )
    
    style_header = ParagraphStyle(
        name='Header',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=COLOR_PRIMARY,
        alignment=1,
        spaceAfter=10,
        spaceBefore=15,
        fontName='Helvetica-Bold',
        borderPadding=5,
        borderColor=COLOR_PRIMARY,
        borderWidth=0,
        leftIndent=0
    )
    
    style_normal = ParagraphStyle(
        name='Normal',
        parent=styles['Normal'],
        fontSize=10,
        leading=15,
        textColor=colors.black,
        alignment=4,
        
    )
    
    style_label = ParagraphStyle(
        name='Label',
        parent=styles['Normal'],
        fontSize=10,
        textColor=COLOR_PRIMARY,
        fontName='Helvetica-Bold',
        spaceAfter=3
    )
    
    style_value = ParagraphStyle(
        name='Value',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        backColor=COLOR_LIGHT,
        borderPadding=8,
        borderColor=colors.HexColor('#EEEEEE'),
        borderWidth=1,
        borderRadius=3
    )
    
    # ===== EN-TÊTE PROFESSIONNEL =====
    
    # En-tête avec cadre
    header_content = f"""
    <b>CABINET VÉTÉRINAIRE</b><br/>
    Dr. {data.get('vet_fullname', '[Nom du vétérinaire]')} • Adresse : {data.get('vet_address', '[Adresse complète]')}<br/>
    Téléphone: {data.get('vet_phone', '[Numéro]')} • Email: {data.get('vet_email', '[Adresse email]')}
    """
    
    header_frame = Table([[Paragraph(header_content, 
                                   ParagraphStyle(name='CabinetInfo', fontSize=10, alignment=1, textColor=COLOR_PRIMARY))]], 
                        colWidths=[16*cm])
    header_frame.setStyle(TableStyle([
        ('BOX', (0,0), (0,0), 0.5, COLOR_SECONDARY),
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#F0F8FF')),
        ('PADDING', (0,0), (0,0), 8),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    
    story.append(header_frame)
    story.append(Spacer(1, 0.5*cm))
    
    # Ligne de séparation décorative
    line = HRFlowable(width="100%", thickness=1, color=COLOR_SECONDARY, 
                     spaceAfter=5, spaceBefore=5,
                     lineCap='round', dash=None)
    story.append(line)
    story.append(Spacer(1, 0.3*cm))
    
    # ===== TITRE PRINCIPAL =====
    
    story.append(Paragraph("ATTESTATION VÉTÉRINAIRE", style_main_title))
    story.append(Spacer(1, 0.1*cm))
    
    # ===== INTRODUCTION =====
    
    intro_text = f"""
    Je soussigné(e), <b>Dr. {data.get('vet_fullname', '[Nom et prénom]')}</b>, 
    vétérinaire diplômé(e) et dûment inscrit(e) à l'Ordre National des Vétérinaires 
    sous le numéro <b>{data.get('vet_registration', "[Numéro d'inscription]")}</b>, 
    certifie avoir procédé ce jour à un examen clinique complet de l'animal dont 
    les caractéristiques sont décrites ci-après :
    """
    
    story.append(Paragraph(intro_text, style_normal))
    story.append(Spacer(1, 0.8*cm))
    
    # ===== INFORMATIONS DE L'ANIMAL =====
    
    # Tableau structuré pour les informations
    animal_info_data = [
        ["Nom de l'animal :", data.get('animal_name', '[Nom]')],
        ["Espèce :", data.get('animal_species', '[Espèce]')],
        ["Race :", data.get('animal_breed', 'Non spécifiée')],
        ["Sexe :", data.get('animal_gender', '[Sexe]')],
        ["Couleur :", data.get('animal_couleur', 'Non spécifié')],
        ["Pucé :", data.get('animal_puce', '[Puce]')],
        ["Propriétaire :", data.get('owner_name', '[Nom du propriétaire]')],
        ["Identification :", data.get('animal_id', '[Numéro]')]
    ]
    
    # Créer le tableau
    animal_data = []
    for label, value in animal_info_data:
        if value:
            animal_data.append([
                Paragraph(f"<b>{label}</b>", style_label),
                Paragraph(value, style_value)
            ])
    
    if animal_data:
        table = Table(animal_data, colWidths=[5*cm, 10*cm])
        table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (0,-1), 10),
            ('RIGHTPADDING', (1,0), (1,-1), 10),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#E8F4F8')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
        ]))
        story.append(table)
    
    story.append(Spacer(1, 0.5*cm))
    
    # ===== RÉSULTATS DE L'EXAMEN =====
    
    story.append(Paragraph("RÉSULTATS DE L'EXAMEN CLINIQUE :", 
                          ParagraphStyle(name='ExamTitle', parent=styles['Heading3'], 
                                       fontSize=13, textColor=COLOR_PRIMARY)))
    story.append(Spacer(1, 0.5*cm))
    
    # Liste des attestations avec icônes
    attestations = [
        ("L'animal est en bonne santé générale et ne présente aucun signe de maladie apparente", data.get('attestation_health', False)),
        ("Les vaccinations obligatoires sont à jour conformément à la réglementation en vigueur", data.get('attestation_vaccination', False)),
        ("L'animal ne présente aucun signe de maladie contagieuse au moment de l'examen", data.get('attestation_disease', False)),
        ("L'animal est apte au transport auquel il est destiné", data.get('attestation_transport', False))
    ]
    
    for text, checked in attestations:
        if checked:
            story.append(Paragraph(f"✓ {text}", 
                                 ParagraphStyle(name='Checked', parent=style_normal, 
                                              textColor=COLOR_SUCCESS)))
        else:
            story.append(Paragraph(f"✗ {text}", 
                                 ParagraphStyle(name='Unchecked', parent=style_normal, 
                                              textColor=colors.grey)))
    
    story.append(Spacer(1, 0.7*cm))
    
    # ===== TEXTE FINAL =====
    
    story.append(Paragraph(
        "La présente attestation est établie pour servir et valoir ce que de droit.",
        ParagraphStyle(name='FinalText', fontSize=10, alignment=1, fontStyle='italic')
    ))
    
    story.append(Spacer(1, 0.3*cm))
    
    # ===== ZONE SIGNATURE ET DATE =====
    
    # Table pour aligner date (gauche) et signature (droite)
    signature_table_data = [
        [   
            # Colonne gauche : Date
            Paragraph(f"<b>Fait à {data.get('city', '[Ville]')}, le {format_date(data.get('date', datetime.now().strftime('%Y-%m-%d')))}</b>", 
                     ParagraphStyle(name='DateCol', fontSize=10, alignment=0)),
            
            # Colonne droite : Signature
            Paragraph("Signature du vétérinaire ", 
                     ParagraphStyle(name='SignatureLabel', fontSize=10, alignment=2))
        ]
    ]
    
    signature_table = Table(signature_table_data, colWidths=[8*cm, 8*cm])
    signature_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('TOPPADDING', (0,0), (-1,-1), 20),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    
    story.append(signature_table)
    
    # Signature numérique si disponible
    if data.get('signature_path') and os.path.exists(data['signature_path']):
        try:
            img_signature = Image(data['signature_path'], width=6*cm, height=2.5*cm)
            img_signature.hAlign = 'RIGHT'
            story.append(img_signature)
        except Exception as e:
            print(f"Erreur signature image: {e}")
    
    # Cachet vétérinaire au CENTRE
    if data.get('stamp_image') and os.path.exists(data['stamp_image']):
        try:
            story.append(Spacer(1, 0.1*cm))
            img_cachet = Image(data['stamp_image'], width=3*cm, height=3*cm)
            img_cachet.hAlign = 'CENTER'
            cachet_table = Table([[img_cachet]], colWidths=[10*cm])
            cachet_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (0,0), 'CENTER'),
                ('VALIGN', (0,0), (0,0), 'TOP'),
                ('TOPPADDING', (0,0), (0,0), -35),  # Pas de padding en haut
                ('BOTTOMPADDING', (0,0), (0,0), 0),  # Pas de padding en bas
            ]))
            story.append(cachet_table)
        except Exception as e:
            print(f"Erreur cachet image: {e}")
    
    # ===== PIED DE PAGE =====
    
    story.append(Spacer(1, 0.7*cm))
    
    # Numéro d'attestation et informations complémentaires
    footer_text = f"""
    <i>N° d'attestation: {data.get('numero_attestation', 'NON-001')} • Document certifié conforme • 
    Établi le {datetime.now().strftime('%d/%m/%Y à %H:%M')} • ID: {attestation_id[:8]}</i>
    """
    
    story.append(Paragraph(footer_text, 
                          ParagraphStyle(name='Footer', fontSize=6, textColor=colors.grey, alignment=1)))
    
    # ===== GÉNÉRATION DU PDF =====
    
    try:
        doc.build(story)
        print(f"✅ Attestation PDF générée: {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"❌ Erreur génération attestation: {e}")
        error_doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        error_story = [
            Paragraph("ERREUR DE GÉNÉRATION", style_main_title),
            Spacer(1, 2*cm),
            Paragraph(f"Erreur: {str(e)}", style_normal)
        ]
        error_doc.build(error_story)
        return pdf_path
        
# ==================== LANCEMENT DE L'APPLICATION ====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
