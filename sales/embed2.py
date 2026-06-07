import re
SHOTS="/app/sales/shots/final"
PLAN={
 "/app/sales/gymaxisai_operators.html":[("Marketing · AI Campaign Studio",f"{SHOTS}/marketing.png","GymAxis Marketing campaigns — Apex Fitness Group")],
 "/app/sales/gymaxisai_engineers.html":[("Stock · Van GX-04",f"{SHOTS}/vanstock.png","GymAxis Engineer van stock")],
}
def find_body_span(html,start):
    open_idx=html.index('<div class="body"',start); depth=0
    for m in re.compile(r"<div\b|</div>").finditer(html,open_idx):
        if m.group()=="</div>":
            depth-=1
            if depth==0: return open_idx,m.end()
        else: depth+=1
    raise ValueError("unbalanced")
for path,items in PLAN.items():
    html=open(path).read()
    for label,src,alt in items:
        anchor=html.index(label)
        o,c=find_body_span(html,anchor)
        html=html[:o]+f'<div class="body shot"><img src="{src}" alt="{alt}"></div>'+html[c:]
        print("embedded",label)
    open(path,"w").write(html)
print("done")
