param([Parameter(Position=0)][string]$Command="health",[Parameter(ValueFromRemainingArguments=$true)][string[]]$Text)
$Base="http://127.0.0.1:11700"
if($Command -eq "health"){Invoke-RestMethod "$Base/health"|ConvertTo-Json -Depth 8;exit}
if($Command -eq "ask"){$body=@{messages=@(@{role="user";content=($Text -join " ")})}|ConvertTo-Json -Depth 5;(Invoke-RestMethod "$Base/api/chat" -Method Post -ContentType "application/json" -Body $body).message.content;exit}
$map=@{mixer="show_mixer";playlist="show_playlist";piano="show_piano_roll";rack="show_channel_rack"};$action=if($map.ContainsKey($Command)){$map[$Command]}else{$Command};$body=@{action=$action}|ConvertTo-Json;Invoke-RestMethod "$Base/api/fl/action" -Method Post -ContentType "application/json" -Body $body|ConvertTo-Json -Depth 5
