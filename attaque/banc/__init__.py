"""Banc d'attaque et de mesure de Dédale.

Le banc n'a aucune capacité offensive réelle. Il ne fait que lire des pages
locales de notre propre surface fictive (leurres/, 8701) et de notre assistant
interne local (interne/, 8702), en boucle fermée sur 127.0.0.1, et suivre ce
qu'il y trouve. Chaque session est étiquetée avec sa vérité terrain pour que le
backend (8700) puisse calculer détection et faux positifs.
"""
