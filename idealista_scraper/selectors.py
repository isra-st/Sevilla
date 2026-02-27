"""Centralized selectors for Idealista HTML. Update here when the site structure changes."""

# Search / listing page
# Main content: section.items-container.items-list > article; link in div.item-info-container > a
H1_TOTAL = "h1#h1-container"
TOTAL_REGEX = r":\s*([0-9,.\s]+)\s+(?:viviendas|houses|pisos)"

# Cards: section with items-list, articles (item-info-container has the /inmueble/ link)
CARDS = "//section[contains(@class,'items-list')]/article"
# Fallback: any article containing an /inmueble/ link (site structure may change)
CARDS_FALLBACK_ARTICLE = "//article[.//a[contains(@href,'/inmueble/')]]"
# Last resort: links to listings (we use the link's closest article or parent as box)
CARDS_FALLBACK_LINKS = "//a[contains(@href,'/inmueble/')]"
CARDS_CSS = "section.items-container.items-list article"
CARD_IS_AD = ".//p[@class='adv_txt']"
CARD_TITLE = ".//div/a/@title"
# Link: div.item-info-container a with href containing /inmueble/
CARD_LINK = ".//div[contains(@class,'item-info-container')]//a[contains(@href,'/inmueble/')]/@href"
CARD_LINK_FALLBACK = ".//a[contains(@href,'/inmueble/')]/@href"
CARD_PRICE = ".//span[contains(@class,'item-price')]/text()"
CARD_CURRENCY = ".//span[contains(@class,'item-price')]/span/text()"
CARD_DETAILS = ".//div[@class='item-detail-char']/span/text()"
# Alternative: div with similar class or any span containing m² / habitaciones (site structure may change)
CARD_DETAILS_ALT = ".//div[contains(@class,'item-detail')]//span/text()"
CARD_DESCRIPTION = ".//div[contains(@class,'item-description')]/p/text()"
CARD_TAGS = ".//div[@class='listing-tags-container']/span/text()"
CARD_SELLER_TITLE = ".//picture[@class='logo-branding']/a/@title"
CARD_SELLER_HREF = ".//picture[@class='logo-branding']/a/@href"

# Detail page (one listing e.g. /inmueble/107621327/)
DETAIL_TITLE = ".main-info__title h1 span::text"
DETAIL_TITLE_FALLBACK = "h1 .main-info__title-main::text"
DETAIL_LOCATION = ".main-info__title span span::text"
DETAIL_LOCATION_FALLBACK = ".main-info__title-minor::text"
DETAIL_PRICE_NODE = ".info-data-price"
DETAIL_PRICE_SPAN = ".info-data span span::text"
DETAIL_PRICE_FALLBACK = ".info-data-price span::text"
DETAIL_DESCRIPTION = ".commentsContainer .comment .adCommentsLanguage p::text"
DETAIL_DESCRIPTION_FALLBACK = "div.comment ::text"
# Extra fallbacks when site structure changes (e.g. different wrapper classes)
DETAIL_DESCRIPTION_ALT = ".comment p::text"
DETAIL_DESCRIPTION_ALT2 = "[class*='comment'] p::text"
DETAIL_DESCRIPTION_ALT3 = "[class*='description'] ::text"
DETAIL_DESCRIPTION_ALT4 = "section[class*='description'] ::text"
DETAIL_UPDATED = "//p[@class='stats-text'][contains(.,'updated') or contains(.,'Actualizado')]/text()"
DETAIL_UPDATED_ALT = "//p[contains(@class,'stats') and (contains(.,'updated') or contains(.,'Actualizado'))]/text()"
DETAIL_UPDATED_ALT2 = "//*[contains(.,'Actualizado') or contains(.,'updated')]/text()"
# Main features: sq m, rooms, feature 3 (nth-child 1, 2, 3)
DETAIL_INFO_FEATURES = ".detail-info section .info-features span::text"
DETAIL_INFO_FEATURES_ALT = ".info-features span::text"
DETAIL_FEATURE_HEADERS = ".details-property-h2"
DETAIL_FEATURE_HEADERS_ALT = "//div[contains(@class,'details-property')]//h2"
DETAIL_FEATURE_HEADERS_ALT2 = "#details .details-property h2"
DETAIL_FEATURE_ITEMS = "following-sibling::div[1]//li"
DETAIL_FEATURE_ITEMS_ALT = "following-sibling::*[1]//li"
# Details sections: #details .details-property .details-property-feature-one, -two, -three
DETAIL_PROPERTY_FEATURE_ONE = "#details .details-property .details-property-feature-one"
DETAIL_PROPERTY_FEATURE_TWO = "#details .details-property .details-property-feature-two"
DETAIL_PROPERTY_FEATURE_THREE = "#details .details-property .details-property-feature-three"
DETAIL_PROPERTY_FEATURE_ONE_ALT = ".details-property-feature-one"
DETAIL_PROPERTY_FEATURE_TWO_ALT = ".details-property-feature-two"
DETAIL_PROPERTY_FEATURE_THREE_ALT = ".details-property-feature-three"
# First picture
DETAIL_PICTURE = ".main-image_first picture img::attr(src)"
DETAIL_PICTURE_ALT = ".main-image picture img::attr(src)"
DETAIL_PICTURE_ALT2 = "[class*='main-image'] img::attr(src)"
DETAIL_PICTURE_ALT3 = ".gallery img::attr(src)"
DETAIL_IMAGES_REGEX = r"fullScreenGalleryPics\s*[=:]\s*(\[.+?\])"
DETAIL_IMAGES_REGEX_ALT = r"galleryPics\s*[=:]\s*(\[.+?\])"
DETAIL_IMAGES_REGEX_ALT2 = r"imageUrl[\"']?\s*:\s*[\"']([^\"']+)"  # single imageUrl in script
