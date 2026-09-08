export const zones=[
{id:"south",name:"South Ward",risk:"Red",mri:88,utci:45,hi:47.5,humidity:79,wind:1.2,vulnerable:35,healthcare:34,mortality:24,population:"1.5L",lat:22.545,lng:88.365,advisory:"Activate cooling centres and emergency heat action plans. Restrict outdoor work during peak afternoon hours."},
{id:"central",name:"Central Ward",risk:"Red",mri:84,utci:44.1,hi:46.8,humidity:76,wind:1.8,vulnerable:31,healthcare:42,mortality:18,population:"1.2L",lat:22.572,lng:88.363,advisory:"Activate cooling centres, issue outdoor-work restrictions, and alert healthcare facilities."},
{id:"west",name:"West Ward",risk:"Orange",mri:73,utci:42.8,hi:45,humidity:73,wind:2,vulnerable:28,healthcare:57,mortality:16,population:"0.9L",lat:22.565,lng:88.335,advisory:"Issue public advisories, inspect cooling centres, and shift outdoor work away from peak heat."},
{id:"north",name:"North Ward",risk:"Orange",mri:65,utci:41.8,hi:44.1,humidity:71,wind:2.4,vulnerable:25,healthcare:64,mortality:12,population:"0.8L",lat:22.615,lng:88.365,advisory:"Monitor closely and open cooling centres if risk increases."},
{id:"industrial",name:"Industrial Ward",risk:"Orange",mri:61,utci:41,hi:43.6,humidity:69,wind:2.2,vulnerable:29,healthcare:61,mortality:11,population:"0.7L",lat:22.555,lng:88.405,advisory:"Shift heavy outdoor work to early morning or evening hours."},
{id:"east",name:"East Ward",risk:"Yellow",mri:46,utci:38.9,hi:41.2,humidity:66,wind:2.8,vulnerable:20,healthcare:72,mortality:7,population:"0.6L",lat:22.585,lng:88.415,advisory:"Maintain routine monitoring and publish heat-safety guidance."},
{id:"lake",name:"Lake Ward",risk:"Yellow",mri:38,utci:37.8,hi:40.1,humidity:64,wind:3.1,vulnerable:18,healthcare:78,mortality:5,population:"0.5L",lat:22.535,lng:88.395,advisory:"Continue monitoring and encourage hydration and shade."},
{id:"harbor",name:"Harbor Ward",risk:"Green",mri:18,utci:33.2,hi:35,humidity:58,wind:3.8,vulnerable:13,healthcare:86,mortality:2,population:"0.4L",lat:22.525,lng:88.345,advisory:"No special action required. Continue normal heat-safety communication."}
];
export const forecast=[
{day:"Today",temp:44,utci:41.2,mri:72,risk:"Orange"},
{day:"Tomorrow",temp:45,utci:42.8,mri:78,risk:"Orange"},
{day:"10 Sep",temp:46,utci:44.1,mri:84,risk:"Red"},
{day:"11 Sep",temp:44,utci:42,mri:76,risk:"Orange"},
{day:"12 Sep",temp:42,utci:39.5,mri:55,risk:"Yellow"}
];
export const facilities=[
{name:"Central General Hospital",type:"Hospital",lat:22.572,lng:88.363,capacity:"42% available"},
{name:"South Emergency Centre",type:"Emergency",lat:22.545,lng:88.365,capacity:"34% available"},
{name:"Lake Community Clinic",type:"Clinic",lat:22.535,lng:88.395,capacity:"78% available"}
];