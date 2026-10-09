(() => {
 const age=document.querySelector('[name="age"]'); if(!age) return;
 function update(){
   const minor=age.value!=='' && Number(age.value)<18;
   for(const name of ['parent_name','parent_phone','mobile']){
     const input=document.querySelector('[name="'+name+'"]'); if(!input) continue;
     const show=name==='mobile' ? !minor : minor;
     input.closest('[data-apply-field]').hidden=!show; input.disabled=!show; input.required=show;
   }
 }
 age.addEventListener('input',update); update();
})();
