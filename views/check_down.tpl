<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" type="text/css" href="https://necolas.github.io/normalize.css/8.0.1/normalize.css">
    <link rel="stylesheet" type="text/css" href="main.css">
    <title>up?</title>
  </head>
  <body>
    <div id="content">
      <h1>down!</h1>
      <div class="message">
        That <a href="{{url}}" target="_blank" rel="noopener noreferrer">link</a> does seem to be down.
      </div>
      <div class="message">
        Submit an email address to get notified when it's up again.
      </div>
      <form action="/submit" method="POST">
        <input type="hidden" name="url" value="{{url}}" />
        <input type="email" name="email" autocomplete="email" placeholder="email" required/>
        <button>Submit</button>
      </form>
      <div class="message">
        <a href="/">Got another link?</a>
      </div>
    </div>
  </body>
</html>
