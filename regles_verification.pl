% =============================================================================
% Brique 2 — Vérification par règles, version ProbLog (Enzo Ferrier)
% Mêmes règles que brique2_verification_regles.py, mais pondérées : chaque affirmation
% reçoit une probabilité d'être soutenue par la connaissance du graphe.
% Les faits (claim/4, negated/1, edge/3, covered/2, general/2, expert_ok/3, expert_ko/3,
% element/1, constraint/2) sont générés par brique2_problog.py à partir de la réponse.
%
% Poids : choisis par le groupe, cohérents avec les poids de la version Python
% (SOUTENUE 1 ; PARTIELLE 0,6 ; NON_VERIFIABLE 0,3 ; NON_SOUTENUE 0,1).
% Sources : provenance des arêtes Hetionet (Himmelstein et al., eLife 2017) ; SIDER 4.1
% (couverture partielle des notices) ; PharmacotherapyDB (« treats » ≠ « palliates »).
% =============================================================================

% R1 — arête présente dans le graphe : soutien fort (0,95 : erreurs résiduelles de la source)
0.95::support(C) :- claim(C, S, R, O), \+ negated(C), edge(S, R, O).

% R2 — relation voisine : « soulage » au lieu de « traite », ou effet plus général présent
voisine(C) :- claim(C, S, ctd, O), edge(S, cpd, O).
voisine(C) :- claim(C, S, ccse, O), general(O, G), edge(S, ccse, G).
0.6::support(C) :- claim(C, _, _, _), \+ negated(C), voisine(C).

% R5 — la source ne couvre pas ce sujet pour cette relation : pas d'information (a priori 0,3)
0.3::support(C) :- claim(C, S, R, O), \+ negated(C), \+ covered(S, R), \+ edge(S, R, O).

% R7 — source couverte mais arête absente : faible soutien (le graphe reste incomplet)
0.1::support(C) :- claim(C, S, R, O), \+ negated(C), covered(S, R), \+ edge(S, R, O), \+ voisine(C).

% R3 — la réponse nie un fait présent : contradiction
contradiction(C) :- claim(C, S, R, O), negated(C), edge(S, R, O).

% R4 — négation sans arête : on ne prouve pas un « non » en monde ouvert
0.3::support(C) :- claim(C, S, R, O), negated(C), \+ edge(S, R, O).

% R8 — corrections de l'expert (connaissance validée, prioritaire)
support(C) :- claim(C, S, R, O), \+ negated(C), expert_ok(S, R, O).
contradiction(C) :- claim(C, S, R, O), \+ negated(C), expert_ko(S, R, O).

% R10 — un élément de réponse est correct si toutes ses contraintes sont soutenues
%        (les règles element_ok/1 sont générées : element_ok(x) :- support(c1), support(c2).)
