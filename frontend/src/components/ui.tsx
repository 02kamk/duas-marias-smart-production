import type {ReactNode} from 'react';
export function Card({children}:{children:ReactNode}){return <section className="card">{children}</section>}
export function Progress({value}:{value:number}){return <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label="Conclusão"><span style={{width:`${value}%`}}/></div>}
export function Risk({value}:{value:number}){return <span className={`badge ${value>=50?'warn':''}`}>MOCK · {value}%</span>}
