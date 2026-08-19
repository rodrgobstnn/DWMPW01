<!DOCTYPE html>
<html lang="es">
    <head>
        <title>Mi primera pagina web</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"></script>
    </head>
    <body>
        <!barra de navegacion>
        <nav class ="navbar navbar navbar-expand-sm bg-dark navbar-dark">
            <div class="container-fluid">
                <a class="navbar-brand" href="index.php"><img src="img/gym.png" alt="logo" height="36"></a>
                <!Cambia el aspecto a 3 barritas en la barra cuando la pantalla es mas pequeña>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#collapsibleNavbar">
                    <span class="navbar-toggler-icon"></span>
                </button>
                
                <div class="collapse navbar-collapse" id="collapsibleNavbar">
                    <ul class="navbar-nav">
                        <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">Empresa</a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="#">Quienes Somos</a></li>
                            <li><a class="dropdown-item" href="#">Nuestro Equipo</a></li>
                            <li><a class="dropdown-item" href="#">Mision</a></li>
                        </ul>
                        </li>

                        <li class="nav-item">
                        <a class="nav-link" href="productos.php">Productos</a>
                        </li>
                        <li class="nav-item">
                        <a class="nav-link" href="servicios.php">Servicios</a>
                        </li>
                        <li class="nav-item">
                        <a class="nav-link" href="contacto.php">Contacto</a>
                        </li>  
                       
                    </ul>
                    </div>
                
            </div>
        </nav>
        <div class="container-fluid bg-secondary">
            Hola Servicios<br>
            <a href="index.php">Volver</a><br>
        </div>
        <!Footer>
        <div class="container-fluid bg-dark">
            <div class="row">
                <div class="col-4"></div>
                <div class="col-4" style="color:white"><strong>@MiEmpresa2026</strong></div>
                <div class="col-4"></div>
            </div>
        </div>
    </body>
</html>

