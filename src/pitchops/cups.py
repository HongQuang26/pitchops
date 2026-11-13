"""Configurable knockout and group-to-knockout Monte Carlo engines.

Goals are regulation-time Poisson draws. Extra time scales both means by 1/3;
shootouts default to 50/50, an explicit uncalibrated scenario assumption.
"""
from collections import Counter
import numpy as np

WC22_SLOTS=[('A1','B2'),('C1','D2'),('E1','F2'),('G1','H2'),('B1','A2'),('D1','C2'),('F1','E2'),('H1','G2')]

def tie_winner(home,away,home_mean,away_mean,rng,legs=1,reverse_means=None,shootout_home=.5):
    if home==away:raise ValueError('A knockout tie needs two different teams')
    if legs not in {1,2}:raise ValueError('Only one-leg and two-leg ties are supported')
    if not 0<=shootout_home<=1:raise ValueError('Invalid shootout probability')
    if min(home_mean,away_mean)<0:raise ValueError('Goal means must be nonnegative')
    h,a=int(rng.poisson(home_mean)),int(rng.poisson(away_mean))
    if legs==2:
        if reverse_means is None:raise ValueError('Two legs require reversed-venue goal means')
        away_second,home_second=reverse_means
        if min(away_second,home_second)<0:raise ValueError('Goal means must be nonnegative')
        h+=int(rng.poisson(home_second));a+=int(rng.poisson(away_second))
        home_mean,away_mean=home_second,away_second
    if h==a:
        h+=int(rng.poisson(home_mean/3));a+=int(rng.poisson(away_mean/3))
    if h==a:return home if rng.random()<shootout_home else away
    return home if h>a else away

def simulate_knockout(teams,means,simulations=3000,seed=42,legs=1,known_winners=None):
    """Adjacent seed pairs, then adjacent winners; no implicit draws/re-seeding.

    means[(home,away)] -> (home_mu,away_mu); all possible pairs must exist.
    known_winners maps a frozenset pair to a previously verified winner.
    """
    teams=list(teams);n=len(teams)
    if simulations<1:raise ValueError('Need at least one simulation')
    if n<2 or n&(n-1) or len(set(teams))!=n:raise ValueError('Unique 2^k teams required')
    rng=np.random.default_rng(seed);titles=Counter();reached=Counter();known_winners=known_winners or {}
    for _ in range(simulations):
        alive=teams[:]
        while len(alive)>1:
            next_round=[]
            for i in range(0,len(alive),2):
                home,away=alive[i:i+2];key=frozenset([home,away])
                if key in known_winners:
                    winner=known_winners[key]
                    if winner not in key:raise ValueError('Known winner is not in its tie')
                else:
                    mu=means.get((home,away))
                    if mu is None:raise ValueError(f'Missing means for {home} vs {away}')
                    winner=tie_winner(home,away,*mu,rng,legs=legs,reverse_means=means.get((away,home)))
                next_round.append(winner);reached[(winner,len(alive)//2)]+=1
            alive=next_round
        titles[alive[0]]+=1
    return [{'team':t,'title':titles[t]/simulations,'final':reached[(t,2)]/simulations if n>2 else 1.0} for t in sorted(teams,key=lambda t:-titles[t])]

def rank_group(teams,results,rng,tiebreak='gd'):
    table={team:[0,0,0] for team in teams}
    for home,away,hg,ag in results:
        if home not in table or away not in table:raise ValueError('Result references a team outside the group')
        table[home][0]+=3 if hg>ag else int(hg==ag);table[away][0]+=3 if ag>hg else int(hg==ag)
        table[home][1]+=hg-ag;table[away][1]+=ag-hg;table[home][2]+=hg;table[away][2]+=ag
    # Group order can use H2H first, or overall goal difference first.
    h2h={t:[0,0,0] for t in teams}
    if tiebreak=='h2h':
        tied={t:{x for x in teams if table[x][0]==table[t][0]} for t in teams}
        for home,away,hg,ag in results:
            if away in tied[home]:
                h2h[home][0]+=3 if hg>ag else int(hg==ag);h2h[away][0]+=3 if ag>hg else int(hg==ag)
                h2h[home][1]+=hg-ag;h2h[away][1]+=ag-hg;h2h[home][2]+=hg;h2h[away][2]+=ag
    elif tiebreak!='gd':raise ValueError('Supported group tiebreaks: gd, h2h')
    return sorted(teams,key=lambda t:(-table[t][0],*[-x for x in h2h[t]],-table[t][1],-table[t][2],rng.random()))

def simulate_world_cup(games,means,as_of,simulations=3000,seed=42):
    """2022 format: eight 4-team groups, fixed R16 slots, no away-goal rule.

    Prior completed ties stay fixed. Fair-play/FIFA-ranking final group tie-break
    is approximated by a random tie only after equal points/GD/GF.
    """
    import pandas as pd
    cutoff=pd.Timestamp(as_of);groups={letter:set() for letter in 'ABCDEFGH'}
    group_games=games[games.stage=='Group Stage']
    for m in group_games.itertuples():
        if m.group_home in groups:groups[m.group_home].add(m.home)
        if m.group_away in groups:groups[m.group_away].add(m.away)
    changed=True
    while changed:
        changed=False
        for m in group_games.itertuples():
            for members in groups.values():
                if m.home in members or m.away in members:
                    before=len(members);members.update([m.home,m.away]);changed|=len(members)>before
    if any(len(members)!=4 for members in groups.values()):raise ValueError('Incomplete World Cup group membership')
    for group,members in groups.items():
        subset=group_games[group_games.home.isin(members)&group_games.away.isin(members)]
        if len(subset)!=6:raise ValueError('Need all six scheduled group pairings, not sampled results')
    fixtures={letter:list(group_games[group_games.home.isin(members)&group_games.away.isin(members)].itertuples()) for letter,members in groups.items()}
    prior=games[(games.date<cutoff)&(games.stage!='Group Stage')]
    known={frozenset([m.home,m.away]):m.winner for m in prior.itertuples() if m.winner and m.stage not in {'3rd Place Final','Third Place Playoff'}}
    rng=np.random.default_rng(seed);titles=Counter();finals=Counter();round16=Counter()
    all_teams=sorted(set(games.home)|set(games.away))
    for _ in range(simulations):
        slots={}
        for letter,members in groups.items():
            results=[]
            for m in fixtures[letter]:
                if m.date<cutoff:hg,ag=m.hg,m.ag
                else:
                    mu=means[(m.home,m.away)];hg,ag=rng.poisson(mu[0]),rng.poisson(mu[1])
                results.append((m.home,m.away,hg,ag))
            order=rank_group(sorted(members),results,rng)
            slots[letter+'1'],slots[letter+'2']=order[:2]
        alive=[slots[slot] for pair in WC22_SLOTS for slot in pair]
        for team in alive:round16[team]+=1
        while len(alive)>1:
            winners=[]
            for i in range(0,len(alive),2):
                home,away=alive[i:i+2];key=frozenset([home,away])
                winner=known.get(key)
                if winner is None:winner=tie_winner(home,away,*means[(home,away)],rng)
                winners.append(winner)
            if len(winners)==2:
                for team in winners:finals[team]+=1
            alive=winners
        titles[alive[0]]+=1
    return {'simulations':simulations,'as_of':str(cutoff.date()),'format':'2022 eight groups + fixed knockout bracket','assumptions':'Frozen strengths; ET 1/3 regulation rate; shootout 50/50; final group fair-play tie replaced by random tie; not a current FIFA/UEFA rule engine for every season.','table':[{'team':t,'title':titles[t]/simulations,'final':finals[t]/simulations,'round16':round16[t]/simulations} for t in sorted(all_teams,key=lambda t:-titles[t])]}
