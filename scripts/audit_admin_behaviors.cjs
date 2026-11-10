const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function environment(){
 const nodes=new Map();
 const get=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',style:{},checked:false,disabled:false,classList:{add(){},remove(){},toggle(){}},addEventListener(){}});return nodes.get(id)};
 const ctx={URL,Headers,console:{error(){},warn(){},log(){}},confirm:()=>true,setTimeout:()=>1,setInterval:()=>1,clearInterval(){},
  events:{},document:{getElementById:get,querySelector:()=>({content:'csrf'}),querySelectorAll:()=>[],addEventListener(name,fn){ctx.events[name]=fn},documentElement:{setAttribute(){}}},
  localStorage:{getItem:()=>null,setItem(){}},location:{href:'http://localhost/admin',origin:'http://localhost'},addEventListener(){},
  network:async()=>({ok:false,status:403,json:async()=>({detail:'Denied'})})};
 ctx.fetch=(...args)=>ctx.network(...args);
 ctx.window=ctx;
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/admin.js'),'utf8'),ctx);
 ctx.toasts=[];ctx.showToast=(...x)=>ctx.toasts.push(x);
 return {ctx,get,run:s=>vm.runInContext(s,ctx)};
}
module.exports={environment};
if(require.main===module){
 const result=require('node:child_process').spawnSync(process.execPath,['--test',path.join(__dirname,'test_admin_behaviors.cjs')],{stdio:'inherit'});
 process.exitCode=result.status??1;
}
